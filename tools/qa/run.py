#!/usr/bin/env python3
"""
QA Orchestrator – single entry-point for the full quality pipeline.

Phases:
  1. (optional) docker compose up -d
  2. Wait for /readyz on all services (polling with backoff)
  3. Lint + type check (ruff, black, mypy)
  4. Unit tests (pytest per service) → JUnit XML + optional coverage
  5. E2E HTTP scenarios
  6. Load test (k6)
  7. Collect docker stats (CPU/memory/restarts)
  8. Generate report → JSON + Markdown + console

Usage:
  python -m tools.qa.run                     # full suite (expects running stack)
  python -m tools.qa.run --compose           # docker compose up first
  python -m tools.qa.run --fast              # lint + unit only
  python -m tools.qa.run --e2e-only          # E2E HTTP only
  python -m tools.qa.run --load-only         # load test only
  python -m tools.qa.run --compose --teardown  # full + teardown
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

import httpx

# Ensure project root is on sys.path so `tools.qa.*` imports resolve.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.qa.config import (
    ARTIFACTS_DIR,
    COMPOSE_FILE,
    COVERAGE_ENABLED,
    DOCKER_STATS_ENABLED,
    DOCKER_STATS_SAMPLES,
    DOCKER_STATS_INTERVAL_S,
    K6_SCRIPT,
    POLL_INTERVAL,
    POLL_MAX_WAIT,
    PROJECT_ROOT as _ROOT,
    REQUEST_TIMEOUT,
    SERVICE_URLS,
    SERVICES,
    UNIT_TEST_ENV,
)
from tools.qa.http_e2e import E2EReport, run_all as run_e2e_all
from tools.qa.report import (
    ContainerStats,
    LoadMetrics,
    PhaseResult,
    QAReport,
    TestStats,
    parse_k6_summary,
    write_reports,
)


# ── Utility ──────────────────────────────────────────────────────────


def _run(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, capture output, never raise on non-zero exit."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd or _ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=run_env,
    )


def _log(icon: str, msg: str) -> None:
    print(f"  {icon}  {msg}", flush=True)


# ── Phases ───────────────────────────────────────────────────────────


def phase_compose_up() -> PhaseResult:
    """Start docker-compose stack."""
    _log("🐳", "Starting docker-compose stack …")
    t0 = time.monotonic()
    r = _run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--build", "--wait"],
        timeout=600,
    )
    dur = (time.monotonic() - t0) * 1000
    ok = r.returncode == 0
    return PhaseResult(
        name="compose_up",
        passed=ok,
        duration_ms=dur,
        detail="Stack started" if ok else r.stderr[-300:],
    )


def phase_wait_ready() -> PhaseResult:
    """Poll /readyz for all services with backoff."""
    _log("⏳", "Waiting for services to become ready …")
    t0 = time.monotonic()
    failures: list[str] = []
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        for svc, url in SERVICE_URLS.items():
            ready = False
            deadline = time.monotonic() + POLL_MAX_WAIT
            backoff = POLL_INTERVAL
            while time.monotonic() < deadline:
                try:
                    resp = client.get(f"{url}/readyz")
                    if resp.status_code == 200:
                        ready = True
                        _log("✓", f"{svc} ready ({url})")
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 10)
            if not ready:
                failures.append(svc)

    dur = (time.monotonic() - t0) * 1000
    if failures:
        return PhaseResult(
            name="readiness",
            passed=False,
            duration_ms=dur,
            detail=f"NOT READY: {', '.join(failures)}",
        )
    return PhaseResult(
        name="readiness",
        passed=True,
        duration_ms=dur,
        detail=f"All {len(SERVICE_URLS)} services ready",
    )


def phase_lint() -> PhaseResult:
    """Run ruff + black + mypy across all services."""
    _log("🔍", "Running lint / format / type checks …")
    t0 = time.monotonic()
    errors: list[str] = []

    for svc in SERVICES:
        svc_dir = os.path.join(_ROOT, "services", svc)
        for tool, cmd in [
            ("ruff", ["ruff", "check", "."]),
            ("black", ["black", "--check", "."]),
            ("mypy", ["mypy", "app/", "--ignore-missing-imports", "--no-error-summary"]),
        ]:
            r = _run(cmd, cwd=svc_dir, timeout=120)
            if r.returncode != 0:
                errors.append(f"{svc}/{tool}: {r.stdout[:200]}")

    # Also lint libs
    for lib in ["libs/contracts", "libs/common"]:
        lib_dir = os.path.join(_ROOT, lib)
        if os.path.isdir(lib_dir):
            for tool, cmd in [
                ("ruff", ["ruff", "check", "."]),
                ("black", ["black", "--check", "."]),
            ]:
                r = _run(cmd, cwd=lib_dir, timeout=60)
                if r.returncode != 0:
                    errors.append(f"{lib}/{tool}: {r.stdout[:200]}")

    dur = (time.monotonic() - t0) * 1000
    if errors:
        return PhaseResult(
            name="lint",
            passed=False,
            duration_ms=dur,
            detail=f"{len(errors)} lint error(s)",
            sub_results=[{"error": e} for e in errors[:10]],
        )
    return PhaseResult(
        name="lint",
        passed=True,
        duration_ms=dur,
        detail="ruff + black + mypy OK",
    )


def phase_unit_tests() -> tuple[PhaseResult, TestStats]:
    """Run pytest per service, collect JUnit XML + optional coverage.

    Returns the phase result and aggregated test statistics.
    """
    _log("🧪", "Running unit tests …")
    t0 = time.monotonic()
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    failures: list[str] = []
    svc_passed = 0
    svc_failed = 0
    stats = TestStats()

    for svc in SERVICES:
        svc_dir = os.path.join(_ROOT, "services", svc)
        svc_junit = os.path.join(ARTIFACTS_DIR, f"junit-{svc}.xml")

        # Build test command
        cmd = [
            "python",
            "-m",
            "pytest",
            "tests/",
            "-v",
            "--tb=short",
            f"--junitxml={svc_junit}",
        ]

        if COVERAGE_ENABLED:
            cov_xml = os.path.join(ARTIFACTS_DIR, f"coverage-{svc}.xml")
            cmd.extend(["--cov=app", f"--cov-report=xml:{cov_xml}", "--cov-report=term-missing:skip-covered"])

        # Build environment: inherit current env + test-specific overrides + PYTHONPATH
        test_env = dict(UNIT_TEST_ENV)
        test_env["PYTHONPATH"] = svc_dir

        r = _run(cmd, cwd=svc_dir, timeout=300, env=test_env)
        if r.returncode != 0:
            failures.append(f"{svc}: {r.stdout[-300:]}")
            svc_failed += 1
        else:
            svc_passed += 1

        # Parse JUnit XML for test statistics
        _parse_junit_stats(svc_junit, svc, stats)

    # Merge coverage if enabled
    if COVERAGE_ENABLED:
        _merge_coverage()

    dur = (time.monotonic() - t0) * 1000
    detail = (
        f"{svc_passed}/{len(SERVICES)} services passed, "
        f"{stats.total_tests} tests ({stats.passed} pass, {stats.failed} fail)"
    )
    if failures:
        return (
            PhaseResult(
                name="unit_tests",
                passed=False,
                duration_ms=dur,
                detail=detail,
                sub_results=[{"error": e} for e in failures],
            ),
            stats,
        )
    return (PhaseResult(name="unit_tests", passed=True, duration_ms=dur, detail=detail), stats)


def _merge_coverage() -> None:
    """Attempt to merge per-service coverage into a single coverage.xml."""
    try:
        import xml.etree.ElementTree as ET

        combined_path = os.path.join(ARTIFACTS_DIR, "coverage.xml")
        cov_files = [
            os.path.join(ARTIFACTS_DIR, f"coverage-{svc}.xml")
            for svc in SERVICES
            if os.path.exists(os.path.join(ARTIFACTS_DIR, f"coverage-{svc}.xml"))
        ]
        if not cov_files:
            return
        # Just copy the first one as "combined" – true merge needs coverage combine
        shutil.copy2(cov_files[0], combined_path)
        _log("📊", f"Coverage report: {combined_path}")
    except Exception:
        pass


def _parse_junit_stats(junit_path: str, svc_name: str, stats: TestStats) -> None:
    """Parse JUnit XML to extract test counts."""
    try:
        import xml.etree.ElementTree as ET

        if not os.path.exists(junit_path):
            return
        tree = ET.parse(junit_path)
        root = tree.getroot()

        # Handle both <testsuites> and <testsuite> root elements
        if root.tag == "testsuites":
            suites = root.findall("testsuite")
        elif root.tag == "testsuite":
            suites = [root]
        else:
            return

        for suite in suites:
            tests = int(suite.get("tests", 0))
            failures = int(suite.get("failures", 0))
            errors = int(suite.get("errors", 0))
            skipped = int(suite.get("skipped", 0))

            stats.total_tests += tests
            stats.failed += failures
            stats.errors += errors
            stats.skipped += skipped
            stats.passed += tests - failures - errors - skipped

        if svc_name not in stats.services_tested:
            stats.services_tested.append(svc_name)
    except Exception:
        pass  # Don't fail the pipeline for stats parsing issues


def phase_e2e() -> PhaseResult:
    """Run HTTP E2E scenarios."""
    _log("🌐", "Running E2E HTTP scenarios …")
    t0 = time.monotonic()
    try:
        e2e_report: E2EReport = run_e2e_all()
    except Exception as exc:
        return PhaseResult(
            name="e2e_http",
            passed=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=str(exc),
        )

    sub = [
        {
            "step": s.name,
            "passed": s.passed,
            "duration_ms": s.duration_ms,
            "detail": s.detail,
            "assertions": s.assertions,
        }
        for s in e2e_report.steps
    ]
    dur = (time.monotonic() - t0) * 1000
    n_pass = sum(1 for s in e2e_report.steps if s.passed)
    n_total = len(e2e_report.steps)
    return PhaseResult(
        name="e2e_http",
        passed=e2e_report.passed,
        duration_ms=dur,
        detail=f"{n_pass}/{n_total} steps passed",
        sub_results=sub,
    )


def phase_load() -> PhaseResult:
    """Run k6 load test."""
    _log("🔥", "Running k6 load test …")
    t0 = time.monotonic()

    if not shutil.which("k6"):
        return PhaseResult(
            name="load_test",
            passed=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail="⚠ k6 not installed – skipped (install: https://k6.io/docs/get-started/installation/)",
        )

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    k6_env: dict[str, str] = {"ARTIFACTS_DIR": ARTIFACTS_DIR}

    r = _run(
        [
            "k6",
            "run",
            "--out",
            f"json={ARTIFACTS_DIR}/k6-results.json",
            K6_SCRIPT,
        ],
        timeout=1800,
        env=k6_env,
    )

    dur = (time.monotonic() - t0) * 1000
    ok = r.returncode == 0
    detail = "k6 passed all thresholds" if ok else f"k6 exit code {r.returncode}"
    if not ok and r.stderr:
        detail += f" – {r.stderr[-200:]}"

    return PhaseResult(name="load_test", passed=ok, duration_ms=dur, detail=detail)


def phase_docker_stats() -> tuple[int, list[ContainerStats]]:
    """Sample container restarts and resource usage.

    Returns (total_restart_count, list[ContainerStats]).
    """
    _log("📊", "Checking container stats …")
    restarts = 0
    stats: list[ContainerStats] = []

    # 1. Check restart counts
    try:
        r = _run(
            ["docker", "compose", "-f", COMPOSE_FILE, "ps", "--format", "json"],
            timeout=30,
        )
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    info = json.loads(line)
                    restarts += info.get("RestartCount", 0)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    # 2. Sample CPU/memory via docker stats
    if DOCKER_STATS_ENABLED:
        try:
            r = _run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}",
                ],
                timeout=30,
            )
            if r.returncode == 0:
                for line in r.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        name = parts[0].strip()
                        cpu_str = parts[1].strip().rstrip("%")
                        mem_usage_str = parts[2].strip()
                        mem_pct_str = parts[3].strip().rstrip("%")

                        try:
                            cpu_pct = float(cpu_str)
                        except ValueError:
                            cpu_pct = 0.0

                        try:
                            mem_pct = float(mem_pct_str)
                        except ValueError:
                            mem_pct = 0.0

                        # Parse memory usage: "123.4MiB / 1.5GiB"
                        mem_usage_mb = 0.0
                        mem_limit_mb = 0.0
                        mem_match = re.match(
                            r"([\d.]+)(MiB|GiB|KiB)\s*/\s*([\d.]+)(MiB|GiB|KiB)",
                            mem_usage_str,
                        )
                        if mem_match:
                            usage_val = float(mem_match.group(1))
                            usage_unit = mem_match.group(2)
                            limit_val = float(mem_match.group(3))
                            limit_unit = mem_match.group(4)

                            mem_usage_mb = _to_mb(usage_val, usage_unit)
                            mem_limit_mb = _to_mb(limit_val, limit_unit)

                        stats.append(
                            ContainerStats(
                                name=name,
                                cpu_pct=cpu_pct,
                                mem_usage_mb=mem_usage_mb,
                                mem_limit_mb=mem_limit_mb,
                                mem_pct=mem_pct,
                            )
                        )
        except Exception:
            pass

    return restarts, stats


def _to_mb(value: float, unit: str) -> float:
    """Convert memory value to MB."""
    if unit == "GiB":
        return value * 1024
    if unit == "KiB":
        return value / 1024
    return value  # MiB


def phase_compose_down() -> PhaseResult:
    """Tear down docker-compose stack."""
    _log("🐳", "Tearing down docker-compose …")
    t0 = time.monotonic()
    r = _run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
        timeout=120,
    )
    dur = (time.monotonic() - t0) * 1000
    return PhaseResult(
        name="compose_down",
        passed=r.returncode == 0,
        duration_ms=dur,
        detail="Stack stopped" if r.returncode == 0 else r.stderr[-200:],
    )


# ── Main ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="QA Orchestrator")
    parser.add_argument("--compose", action="store_true", help="Start docker-compose before tests")
    parser.add_argument("--teardown", action="store_true", help="Tear down docker-compose after tests")
    parser.add_argument("--fast", action="store_true", help="Lint + unit tests only")
    parser.add_argument("--e2e-only", action="store_true", help="E2E HTTP only (services must be running)")
    parser.add_argument("--load-only", action="store_true", help="Load test only (services must be running)")
    args = parser.parse_args()

    t_global = time.monotonic()
    report = QAReport()

    print("\n" + "═" * 60)
    print("  QA PIPELINE")
    print("═" * 60 + "\n")

    # ── 1. Compose up ─────────────────────────────────────────
    if args.compose:
        p = phase_compose_up()
        report.add_phase(p)
        if not p.passed:
            report.total_duration_s = time.monotonic() - t_global
            write_reports(report)
            return 1

    # ── 2. Readiness ──────────────────────────────────────────
    if not args.fast:
        p = phase_wait_ready()
        report.add_phase(p)
        if not p.passed:
            _log("⚠", "Services not ready – skipping live tests")
    else:
        p = PhaseResult(name="readiness", passed=True, detail="skipped (--fast)")

    # ── 3. Lint + type ────────────────────────────────────────
    if not args.e2e_only and not args.load_only:
        report.add_phase(phase_lint())

    # ── 4. Unit tests ─────────────────────────────────────────
    if not args.e2e_only and not args.load_only:
        ut_result, test_stats = phase_unit_tests()
        report.add_phase(ut_result)
        report.test_stats = test_stats

    if args.fast:
        report.total_duration_s = time.monotonic() - t_global
        write_reports(report)
        return 0 if report.overall_pass else 1

    # ── 5. E2E HTTP ───────────────────────────────────────────
    if not args.load_only:
        if p.passed:  # only if services are ready
            report.add_phase(phase_e2e())

    # ── 6. Load test ──────────────────────────────────────────
    if not args.e2e_only and not args.fast:
        if p.passed:
            load_result = phase_load()
            report.add_phase(load_result)
            # Parse k6 metrics
            k6_json = os.path.join(ARTIFACTS_DIR, "k6-summary.json")
            lm = parse_k6_summary(k6_json)
            if lm:
                report.load_metrics = lm

    # ── 7. Docker stats ──────────────────────────────────────
    restarts, container_stats = phase_docker_stats()
    report.container_restarts = restarts
    report.container_stats = container_stats

    # ── 8. Report ─────────────────────────────────────────────
    report.total_duration_s = time.monotonic() - t_global
    write_reports(report)

    # ── 9. Teardown ───────────────────────────────────────────
    if args.teardown:
        report.add_phase(phase_compose_down())

    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
