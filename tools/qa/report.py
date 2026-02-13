"""
Report generator – produces console, JSON and Markdown outputs.

Enterprise-grade reporting with:
  - PASS/FAIL table per phase
  - SLO compliance scoring (percentage)
  - Load test SLO breakdown with thresholds
  - Top 5 slowest endpoints (p95/p99)
  - Error frequency breakdown (status + category)
  - Automated recommendations engine (context-aware)
  - Docker container stats (CPU / memory)
  - Test count statistics
  - Links to generated artifacts
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from tools.qa.config import (
    ARTIFACTS_DIR,
    SLO_ERROR_RATE_PCT,
    SLO_MAX_RESTARTS,
    SLO_READ_P95_MS,
    SLO_WRITE_P95_MS,
)

# Optional rich for pretty console output
try:
    from rich.console import Console
    from rich.table import Table

    _RICH = True
except ImportError:
    _RICH = False


# ── Data models ──────────────────────────────────────────────────────


@dataclass
class PhaseResult:
    name: str
    passed: bool
    duration_ms: float = 0.0
    detail: str = ""
    sub_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EndpointStat:
    name: str
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    avg_ms: float = 0.0
    max_ms: float = 0.0
    min_ms: float = 0.0
    count: int = 0


@dataclass
class ErrorBreakdown:
    total_errors: int = 0
    http_4xx: int = 0
    http_5xx: int = 0
    timeouts: int = 0
    error_rate_pct: float = 0.0


@dataclass
class ContainerStats:
    """Sampled docker stats for a container."""
    name: str
    cpu_pct: float = 0.0
    mem_usage_mb: float = 0.0
    mem_limit_mb: float = 0.0
    mem_pct: float = 0.0


@dataclass
class LoadMetrics:
    total_requests: int = 0
    error_count: int = 0
    error_rate_pct: float = 0.0
    throughput_rps: float = 0.0
    read_p50_ms: float = 0.0
    read_p95_ms: float = 0.0
    read_p99_ms: float = 0.0
    write_p50_ms: float = 0.0
    write_p95_ms: float = 0.0
    write_p99_ms: float = 0.0
    patch_p50_ms: float = 0.0
    patch_p95_ms: float = 0.0
    patch_p99_ms: float = 0.0
    slo_error_rate_ok: bool = True
    slo_read_p95_ok: bool = True
    slo_write_p95_ok: bool = True
    endpoint_stats: list[EndpointStat] = field(default_factory=list)
    error_breakdown: ErrorBreakdown = field(default_factory=ErrorBreakdown)


@dataclass
class TestStats:
    """Aggregated test statistics across all services."""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    services_tested: list[str] = field(default_factory=list)


@dataclass
class QAReport:
    timestamp: str = ""
    total_duration_s: float = 0.0
    overall_pass: bool = True
    compliance_score: float = 0.0
    phases: list[PhaseResult] = field(default_factory=list)
    load_metrics: LoadMetrics | None = None
    test_stats: TestStats = field(default_factory=TestStats)
    recommendations: list[str] = field(default_factory=list)
    container_restarts: int = 0
    container_stats: list[ContainerStats] = field(default_factory=list)

    def add_phase(self, phase: PhaseResult) -> None:
        self.phases.append(phase)
        if not phase.passed:
            self.overall_pass = False

    def finalize(self) -> None:
        self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.container_restarts > SLO_MAX_RESTARTS:
            self.overall_pass = False
        self._compute_compliance_score()
        self._generate_recommendations()

    def _compute_compliance_score(self) -> None:
        """Compute a 0-100 compliance score based on all checks."""
        checks: list[bool] = []

        # Phase results
        for p in self.phases:
            checks.append(p.passed)

        # SLO checks from load metrics
        if self.load_metrics:
            lm = self.load_metrics
            checks.append(lm.slo_error_rate_ok)
            checks.append(lm.slo_read_p95_ok)
            checks.append(lm.slo_write_p95_ok)
            checks.append(lm.error_breakdown.http_5xx == 0)
            checks.append(lm.error_breakdown.timeouts == 0)

        # Container health
        checks.append(self.container_restarts == 0)
        for cs in self.container_stats:
            checks.append(cs.mem_pct < 85)
            checks.append(cs.cpu_pct < 90)

        if checks:
            self.compliance_score = round(sum(1 for c in checks if c) / len(checks) * 100, 1)
        else:
            self.compliance_score = 100.0 if self.overall_pass else 0.0

    def _generate_recommendations(self) -> None:
        recs = self.recommendations
        if self.load_metrics:
            lm = self.load_metrics
            if not lm.slo_read_p95_ok:
                recs.append(
                    f"🔴 Read p95 ({lm.read_p95_ms:.0f}ms) exceeds SLO ({SLO_READ_P95_MS}ms). "
                    "Consider: DB index optimization, query result caching (Redis), "
                    "or increasing SQLAlchemy pool_size."
                )
            if not lm.slo_write_p95_ok:
                recs.append(
                    f"🔴 Write p95 ({lm.write_p95_ms:.0f}ms) exceeds SLO ({SLO_WRITE_P95_MS}ms). "
                    "Check DB pool exhaustion (max_overflow); consider write batching "
                    "or async commit mode."
                )
            if not lm.slo_error_rate_ok:
                recs.append(
                    f"🔴 Error rate ({lm.error_rate_pct:.2f}%) exceeds SLO ({SLO_ERROR_RATE_PCT}%). "
                    "Investigate: connection pool exhaustion, OOM, Kafka backpressure, "
                    "or rate limiting configuration."
                )
            if lm.read_p99_ms > SLO_READ_P95_MS * 3:
                recs.append(
                    f"🟡 Read p99 ({lm.read_p99_ms:.0f}ms) is >3× the p95 SLO. "
                    "Tail latency indicates GC pauses, lock contention, or missing indexes. "
                    "Run EXPLAIN ANALYZE on slow queries."
                )
            if lm.write_p99_ms > SLO_WRITE_P95_MS * 2:
                recs.append(
                    f"🟡 Write p99 ({lm.write_p99_ms:.0f}ms) is >2× the p95 SLO. "
                    "Tune pool_size/max_overflow or enable async DB commits."
                )
            if lm.throughput_rps < 50:
                recs.append(
                    "🟡 Throughput < 50 req/s. Add uvicorn workers (--workers N), "
                    "enable HTTP/2, or scale horizontally."
                )
            if lm.error_breakdown.http_5xx > 0:
                recs.append(
                    f"🔴 {lm.error_breakdown.http_5xx} HTTP 5xx errors detected. "
                    "Check service logs: unhandled exceptions, OOM, or DB connection failures. "
                    "Ensure all exception handlers are registered."
                )
            if lm.error_breakdown.timeouts > 0:
                recs.append(
                    f"🟡 {lm.error_breakdown.timeouts} request timeout(s). "
                    "Increase pool_size/max_overflow, add request queue, "
                    "or implement circuit breaker pattern."
                )
            # Endpoint-specific recommendations
            for ep in lm.endpoint_stats:
                if ep.p95_ms > SLO_READ_P95_MS * 2 and "list" in ep.name.lower():
                    recs.append(
                        f"🟡 Endpoint {ep.name} p95={ep.p95_ms:.0f}ms (>2× SLO). "
                        "Add composite DB indexes, enable query caching, or reduce default page_size."
                    )
                if ep.p99_ms > 5000:
                    recs.append(
                        f"🟡 Endpoint {ep.name} p99={ep.p99_ms:.0f}ms (>5s). "
                        "This endpoint has severe tail latency. Profile with cProfile or py-spy."
                    )

        if self.container_restarts > 0:
            recs.append(
                f"🔴 {self.container_restarts} container restart(s) detected. "
                "Check: OOM kills (docker inspect), healthcheck config, uncaught exceptions."
            )

        # Check container resources
        for cs in self.container_stats:
            if cs.mem_pct > 85:
                recs.append(
                    f"🟡 Container {cs.name} memory at {cs.mem_pct:.0f}% "
                    f"({cs.mem_usage_mb:.0f}MB / {cs.mem_limit_mb:.0f}MB). "
                    "Increase memory limits or investigate leaks with tracemalloc."
                )
            if cs.cpu_pct > 90:
                recs.append(
                    f"🟡 Container {cs.name} CPU at {cs.cpu_pct:.0f}%. "
                    "Add replicas, optimize hot paths, or increase CPU limits."
                )

        # Phase-specific recommendations
        for p in self.phases:
            if p.name == "lint" and not p.passed:
                recs.append(
                    "🟡 Lint failures detected. Enforce in CI with ruff check --fix "
                    "and black --check. Add pre-commit hooks."
                )
            if p.name == "unit_tests" and not p.passed:
                recs.append(
                    "🔴 Unit tests MUST pass. Fix failures before any integration/load testing. "
                    "Run with -x to stop on first failure."
                )
            if p.name == "e2e_http" and not p.passed:
                recs.append(
                    "🔴 E2E tests failed. Functional regressions must be fixed before "
                    "load testing. Check service connectivity and data consistency."
                )

        if not recs:
            recs.append("✅ All checks passed. System is within SLO bounds. Ready for production.")


# ── Report writers ───────────────────────────────────────────────────


def write_reports(report: QAReport) -> None:
    """Write JSON, Markdown, and console reports."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    report.finalize()
    _write_json(report)
    _write_markdown(report)
    _write_console(report)


def _write_json(report: QAReport) -> None:
    path = os.path.join(ARTIFACTS_DIR, "report.json")
    data = _to_dict(report)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  📄 JSON report: {path}")


def _write_markdown(report: QAReport) -> None:
    path = os.path.join(ARTIFACTS_DIR, "report.md")
    lines = [
        f"# QA Report – {report.timestamp}",
        "",
        f"**Overall**: {'✅ PASS' if report.overall_pass else '❌ FAIL'}  ",
        f"**Compliance Score**: {report.compliance_score:.1f}%  ",
        f"**Duration**: {report.total_duration_s:.1f}s  ",
        f"**Container restarts**: {report.container_restarts}",
        "",
    ]

    # Test statistics
    ts = report.test_stats
    if ts.total_tests > 0:
        lines += [
            "## Test Statistics",
            "",
            f"| Metric | Count |",
            f"|--------|-------|",
            f"| Total tests | {ts.total_tests} |",
            f"| Passed | {ts.passed} |",
            f"| Failed | {ts.failed} |",
            f"| Errors | {ts.errors} |",
            f"| Skipped | {ts.skipped} |",
            f"| Services | {', '.join(ts.services_tested)} |",
            "",
        ]

    lines += [
        "## Phases",
        "",
        "| Phase | Status | Duration | Detail |",
        "|-------|--------|----------|--------|",
    ]
    for p in report.phases:
        status = "✅ PASS" if p.passed else "❌ FAIL"
        dur = f"{p.duration_ms:.0f}ms"
        lines.append(f"| {p.name} | {status} | {dur} | {p.detail[:80]} |")

    if report.load_metrics:
        lm = report.load_metrics
        lines += [
            "",
            "## Load Test Metrics",
            "",
            "| Metric | Value | SLO | Status |",
            "|--------|-------|-----|--------|",
            f"| Total requests | {lm.total_requests:,} | – | – |",
            f"| Throughput | {lm.throughput_rps:.1f} req/s | – | – |",
            f"| Error rate | {lm.error_rate_pct:.2f}% | < {SLO_ERROR_RATE_PCT}% | {'✅' if lm.slo_error_rate_ok else '❌'} |",
            f"| Read p50 | {lm.read_p50_ms:.0f}ms | – | – |",
            f"| Read p95 | {lm.read_p95_ms:.0f}ms | < {SLO_READ_P95_MS}ms | {'✅' if lm.slo_read_p95_ok else '❌'} |",
            f"| Read p99 | {lm.read_p99_ms:.0f}ms | – | – |",
            f"| Write p50 | {lm.write_p50_ms:.0f}ms | – | – |",
            f"| Write p95 | {lm.write_p95_ms:.0f}ms | < {SLO_WRITE_P95_MS}ms | {'✅' if lm.slo_write_p95_ok else '❌'} |",
            f"| Write p99 | {lm.write_p99_ms:.0f}ms | – | – |",
            f"| Patch p50 | {lm.patch_p50_ms:.0f}ms | – | – |",
            f"| Patch p95 | {lm.patch_p95_ms:.0f}ms | < {SLO_WRITE_P95_MS}ms | {'✅' if lm.patch_p95_ms < SLO_WRITE_P95_MS else '❌'} |",
            f"| Patch p99 | {lm.patch_p99_ms:.0f}ms | – | – |",
        ]

        # Top 5 slowest endpoints
        if lm.endpoint_stats:
            sorted_eps = sorted(lm.endpoint_stats, key=lambda e: e.p95_ms, reverse=True)[:5]
            lines += [
                "",
                "### Top 5 Slowest Endpoints (p95)",
                "",
                "| Rank | Endpoint | p50 | p95 | p99 | Max | Count |",
                "|------|----------|-----|-----|-----|-----|-------|",
            ]
            for i, ep in enumerate(sorted_eps, 1):
                lines.append(
                    f"| {i} | {ep.name} | {ep.p50_ms:.0f}ms | {ep.p95_ms:.0f}ms | "
                    f"{ep.p99_ms:.0f}ms | {ep.max_ms:.0f}ms | {ep.count:,} |"
                )

        # Error breakdown
        eb = lm.error_breakdown
        if eb.total_errors > 0:
            lines += [
                "",
                "### Error Breakdown",
                "",
                "| Category | Count | % of Total |",
                "|----------|-------|-----------|",
                f"| HTTP 4xx (unexpected) | {eb.http_4xx} | {eb.http_4xx / max(eb.total_errors, 1) * 100:.1f}% |",
                f"| HTTP 5xx | {eb.http_5xx} | {eb.http_5xx / max(eb.total_errors, 1) * 100:.1f}% |",
                f"| Timeouts | {eb.timeouts} | {eb.timeouts / max(eb.total_errors, 1) * 100:.1f}% |",
                f"| **Total** | **{eb.total_errors}** | **100%** |",
            ]

    # Container stats
    if report.container_stats:
        lines += [
            "",
            "## Container Resource Usage",
            "",
            "| Container | CPU % | Memory | Mem % | Status |",
            "|-----------|-------|--------|-------|--------|",
        ]
        for cs in report.container_stats:
            status = "✅" if cs.mem_pct < 85 and cs.cpu_pct < 90 else "⚠️"
            lines.append(
                f"| {cs.name} | {cs.cpu_pct:.1f}% | "
                f"{cs.mem_usage_mb:.0f}MB / {cs.mem_limit_mb:.0f}MB | {cs.mem_pct:.1f}% | {status} |"
            )

    if report.recommendations:
        lines += ["", "## Recommendations", ""]
        for i, r in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {r}")

    # Compliance summary
    lines += [
        "",
        "## Compliance Summary",
        "",
        f"**Score**: {report.compliance_score:.1f}%  ",
        f"**Verdict**: {'✅ COMPLIANT' if report.compliance_score >= 80 else '❌ NON-COMPLIANT'}  ",
        "",
        "| Threshold | Required |",
        "|-----------|----------|",
        "| ≥ 95% | Production-ready |",
        "| 80-94% | Acceptable with warnings |",
        "| < 80% | Non-compliant, requires remediation |",
    ]

    lines += [
        "",
        "## Artifacts",
        "",
        f"- `{ARTIFACTS_DIR}/report.json`",
        f"- `{ARTIFACTS_DIR}/report.md`",
        f"- `{ARTIFACTS_DIR}/k6-summary.json` (if load test ran)",
        f"- `{ARTIFACTS_DIR}/junit-*.xml` (per-service test results)",
        f"- `{ARTIFACTS_DIR}/coverage.xml` (if coverage enabled)",
    ]

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  📄 Markdown report: {path}")


def _write_console(report: QAReport) -> None:
    if _RICH:
        _rich_console(report)
    else:
        _plain_console(report)


def _rich_console(report: QAReport) -> None:
    console = Console()
    console.print()
    console.rule("[bold]QA Report[/bold]")

    # Compliance score
    score = report.compliance_score
    score_color = "green" if score >= 95 else "yellow" if score >= 80 else "red"
    console.print(f"\n[bold]Compliance Score:[/bold] [{score_color}]{score:.1f}%[/{score_color}]")

    # Test stats
    ts = report.test_stats
    if ts.total_tests > 0:
        console.print(
            f"[bold]Tests:[/bold] {ts.total_tests} total, "
            f"[green]{ts.passed} passed[/green], "
            f"[red]{ts.failed} failed[/red], "
            f"{ts.errors} errors, {ts.skipped} skipped"
        )

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Phase")
    table.add_column("Status")
    table.add_column("Duration")
    table.add_column("Detail")

    for p in report.phases:
        status = "[green]PASS[/green]" if p.passed else "[red]FAIL[/red]"
        table.add_row(p.name, status, f"{p.duration_ms:.0f}ms", p.detail[:80])

    console.print(table)

    if report.load_metrics:
        lm = report.load_metrics
        console.print(
            f"\n[bold]Load:[/bold] {lm.total_requests:,} reqs, "
            f"{lm.throughput_rps:.1f} rps, "
            f"err={lm.error_rate_pct:.2f}%, "
            f"read_p95={lm.read_p95_ms:.0f}ms, "
            f"write_p95={lm.write_p95_ms:.0f}ms, "
            f"patch_p95={lm.patch_p95_ms:.0f}ms"
        )

        # Top 5 slowest
        if lm.endpoint_stats:
            console.print("\n[bold]Top 5 Slowest Endpoints (p95):[/bold]")
            ep_table = Table(show_header=True, header_style="bold yellow")
            ep_table.add_column("#", justify="right")
            ep_table.add_column("Endpoint")
            ep_table.add_column("p50", justify="right")
            ep_table.add_column("p95", justify="right")
            ep_table.add_column("p99", justify="right")
            ep_table.add_column("Count", justify="right")
            for i, ep in enumerate(sorted(lm.endpoint_stats, key=lambda e: e.p95_ms, reverse=True)[:5], 1):
                ep_table.add_row(
                    str(i), ep.name,
                    f"{ep.p50_ms:.0f}ms", f"{ep.p95_ms:.0f}ms", f"{ep.p99_ms:.0f}ms",
                    f"{ep.count:,}",
                )
            console.print(ep_table)

        # Error breakdown
        eb = lm.error_breakdown
        if eb.total_errors > 0:
            console.print(
                f"\n[bold]Errors:[/bold] {eb.total_errors} total "
                f"(4xx={eb.http_4xx}, 5xx={eb.http_5xx}, timeouts={eb.timeouts})"
            )

    # Container stats
    if report.container_stats:
        console.print("\n[bold]Container Resources:[/bold]")
        cs_table = Table(show_header=True, header_style="bold magenta")
        cs_table.add_column("Container")
        cs_table.add_column("CPU %", justify="right")
        cs_table.add_column("Memory", justify="right")
        cs_table.add_column("Mem %", justify="right")
        cs_table.add_column("Status")
        for cs in report.container_stats:
            mem_style = "[red]" if cs.mem_pct > 85 else "[green]"
            status = "✅" if cs.mem_pct < 85 and cs.cpu_pct < 90 else "⚠️"
            cs_table.add_row(
                cs.name,
                f"{cs.cpu_pct:.1f}%",
                f"{cs.mem_usage_mb:.0f}MB/{cs.mem_limit_mb:.0f}MB",
                f"{mem_style}{cs.mem_pct:.1f}%",
                status,
            )
        console.print(cs_table)

    if report.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for i, r in enumerate(report.recommendations, 1):
            console.print(f"  {i}. {r}")

    verdict = (
        "[bold green]✅ OVERALL PASS[/bold green]"
        if report.overall_pass
        else "[bold red]❌ OVERALL FAIL[/bold red]"
    )
    console.print(f"\n{verdict}  (score: {report.compliance_score:.1f}%, duration: {report.total_duration_s:.1f}s)\n")


def _plain_console(report: QAReport) -> None:
    print("\n" + "=" * 60)
    print("  QA REPORT")
    print("=" * 60)

    score = report.compliance_score
    print(f"  Compliance Score: {score:.1f}%")

    ts = report.test_stats
    if ts.total_tests > 0:
        print(
            f"  Tests: {ts.total_tests} total, {ts.passed} passed, "
            f"{ts.failed} failed, {ts.errors} errors, {ts.skipped} skipped"
        )

    print()
    for p in report.phases:
        icon = "✅" if p.passed else "❌"
        print(f"  {icon} {p.name:<25} {p.duration_ms:>8.0f}ms  {p.detail[:50]}")

    if report.load_metrics:
        lm = report.load_metrics
        print(
            f"\n  Load: {lm.total_requests:,} reqs, {lm.throughput_rps:.1f} rps, "
            f"err={lm.error_rate_pct:.2f}%, "
            f"read_p95={lm.read_p95_ms:.0f}ms, write_p95={lm.write_p95_ms:.0f}ms, "
            f"patch_p95={lm.patch_p95_ms:.0f}ms"
        )

        if lm.endpoint_stats:
            print("\n  Top 5 Slowest Endpoints (p95):")
            for i, ep in enumerate(sorted(lm.endpoint_stats, key=lambda e: e.p95_ms, reverse=True)[:5], 1):
                print(
                    f"    {i}. {ep.name:<30} p95={ep.p95_ms:>6.0f}ms  "
                    f"p99={ep.p99_ms:>6.0f}ms  n={ep.count:,}"
                )

        eb = lm.error_breakdown
        if eb.total_errors > 0:
            print(
                f"\n  Errors: {eb.total_errors} total "
                f"(4xx={eb.http_4xx}, 5xx={eb.http_5xx}, timeouts={eb.timeouts})"
            )

    if report.container_stats:
        print("\n  Container Resources:")
        for cs in report.container_stats:
            status = "✅" if cs.mem_pct < 85 and cs.cpu_pct < 90 else "⚠️"
            print(
                f"    {status} {cs.name:<30} CPU={cs.cpu_pct:>5.1f}%  "
                f"MEM={cs.mem_usage_mb:.0f}MB/{cs.mem_limit_mb:.0f}MB ({cs.mem_pct:.0f}%)"
            )

    if report.recommendations:
        print("\n  Recommendations:")
        for i, r in enumerate(report.recommendations, 1):
            print(f"    {i}. {r}")

    verdict = "✅ OVERALL PASS" if report.overall_pass else "❌ OVERALL FAIL"
    print(f"\n  {verdict}  (score: {report.compliance_score:.1f}%, duration: {report.total_duration_s:.1f}s)")
    print("=" * 60 + "\n")


def _to_dict(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in asdict(obj).items()}
    return obj


# ── k6 JSON parser ───────────────────────────────────────────────────


def parse_k6_summary(path: str) -> LoadMetrics | None:
    """Parse k6 JSON summary (from handleSummary) into LoadMetrics."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    metrics = data.get("metrics", {})

    def _val(metric_name: str, stat: str, default: float = 0.0) -> float:
        m = metrics.get(metric_name, {})
        vals = m.get("values", {})
        return float(vals.get(stat, default))

    total_reqs = int(_val("http_reqs", "count"))
    iter_max_ms = _val("iteration_duration", "max")
    duration_s = iter_max_ms / 1000 if iter_max_ms else 1.0

    lm = LoadMetrics(
        total_requests=total_reqs,
        error_count=int(_val("errors_total", "count")),
        error_rate_pct=_val("error_rate", "rate") * 100,
        throughput_rps=total_reqs / max(duration_s, 1),
        read_p50_ms=_val("read_latency", "med"),
        read_p95_ms=_val("read_latency", "p(95)"),
        read_p99_ms=_val("read_latency", "p(99)"),
        write_p50_ms=_val("write_latency", "med"),
        write_p95_ms=_val("write_latency", "p(95)"),
        write_p99_ms=_val("write_latency", "p(99)"),
        patch_p50_ms=_val("patch_latency", "med"),
        patch_p95_ms=_val("patch_latency", "p(95)"),
        patch_p99_ms=_val("patch_latency", "p(99)"),
    )

    lm.slo_error_rate_ok = lm.error_rate_pct < SLO_ERROR_RATE_PCT
    lm.slo_read_p95_ok = lm.read_p95_ms < SLO_READ_P95_MS
    lm.slo_write_p95_ok = lm.write_p95_ms < SLO_WRITE_P95_MS

    # Parse endpoint-level stats
    endpoint_metrics = data.get("endpoint_metrics", {})
    ep_name_map = {
        "endpoint_list_pois": "GET /pois",
        "endpoint_list_assets": "GET /assets",
        "endpoint_list_scripts": "GET /scripts",
        "endpoint_list_renders": "GET /renders",
        "endpoint_create_poi": "POST /pois",
        "endpoint_create_asset": "POST /assets",
        "endpoint_patch_poi": "PATCH /pois/{id}",
        "endpoint_health": "GET /healthz",
    }
    for metric_key, display_name in ep_name_map.items():
        ep_data = endpoint_metrics.get(metric_key)
        if ep_data:
            lm.endpoint_stats.append(
                EndpointStat(
                    name=display_name,
                    p50_ms=ep_data.get("p50", 0),
                    p95_ms=ep_data.get("p95", 0),
                    p99_ms=ep_data.get("p99", 0),
                    avg_ms=ep_data.get("avg", 0),
                    max_ms=ep_data.get("max", 0),
                    min_ms=ep_data.get("min", 0),
                    count=int(ep_data.get("count", 0)),
                )
            )

    # Fallback: parse from metrics directly (older k6 format)
    if not lm.endpoint_stats:
        for metric_key, display_name in ep_name_map.items():
            m = metrics.get(metric_key, {})
            vals = m.get("values", {})
            if vals:
                lm.endpoint_stats.append(
                    EndpointStat(
                        name=display_name,
                        p50_ms=float(vals.get("med", 0)),
                        p95_ms=float(vals.get("p(95)", 0)),
                        p99_ms=float(vals.get("p(99)", 0)),
                        avg_ms=float(vals.get("avg", 0)),
                        max_ms=float(vals.get("max", 0)),
                        min_ms=float(vals.get("min", 0)),
                        count=int(vals.get("count", 0)),
                    )
                )

    # Parse error breakdown
    eb = data.get("error_breakdown")
    if eb:
        lm.error_breakdown = ErrorBreakdown(
            total_errors=eb.get("total_errors", 0),
            http_4xx=eb.get("http_4xx", 0),
            http_5xx=eb.get("http_5xx", 0),
            timeouts=eb.get("timeouts", 0),
            error_rate_pct=eb.get("error_rate_pct", 0),
        )
    else:
        lm.error_breakdown = ErrorBreakdown(
            total_errors=int(_val("errors_total", "count")),
            http_4xx=int(_val("http_4xx", "count")),
            http_5xx=int(_val("http_5xx", "count")),
            timeouts=int(_val("timeouts_total", "count")),
            error_rate_pct=lm.error_rate_pct,
        )

    return lm
