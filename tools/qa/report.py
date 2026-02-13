"""
Report generator – produces console, JSON and Markdown outputs.

Consumes results from all QA phases (lint, unit tests, E2E, load)
and writes actionable reports to ``artifacts/qa/``.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
    slo_error_rate_ok: bool = True
    slo_read_p95_ok: bool = True
    slo_write_p95_ok: bool = True


@dataclass
class QAReport:
    timestamp: str = ""
    total_duration_s: float = 0.0
    overall_pass: bool = True
    phases: list[PhaseResult] = field(default_factory=list)
    load_metrics: LoadMetrics | None = None
    recommendations: list[str] = field(default_factory=list)
    container_restarts: int = 0

    def add_phase(self, phase: PhaseResult) -> None:
        self.phases.append(phase)
        if not phase.passed:
            self.overall_pass = False

    def finalize(self) -> None:
        self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.container_restarts > SLO_MAX_RESTARTS:
            self.overall_pass = False
        self._generate_recommendations()

    def _generate_recommendations(self) -> None:
        recs = self.recommendations
        if self.load_metrics:
            lm = self.load_metrics
            if not lm.slo_read_p95_ok:
                recs.append(
                    f"🔴 Read p95 ({lm.read_p95_ms:.0f}ms) exceeds SLO ({SLO_READ_P95_MS}ms). "
                    "Consider adding DB indexes, enabling query caching, or increasing connection pool."
                )
            if not lm.slo_write_p95_ok:
                recs.append(
                    f"🔴 Write p95 ({lm.write_p95_ms:.0f}ms) exceeds SLO ({SLO_WRITE_P95_MS}ms). "
                    "Check DB pool exhaustion; consider write batching or async commit."
                )
            if not lm.slo_error_rate_ok:
                recs.append(
                    f"🔴 Error rate ({lm.error_rate_pct:.2f}%) exceeds SLO ({SLO_ERROR_RATE_PCT}%). "
                    "Check for connection pool exhaustion, OOM, or Kafka backpressure."
                )
            if lm.read_p99_ms > SLO_READ_P95_MS * 3:
                recs.append(
                    f"🟡 Read p99 ({lm.read_p99_ms:.0f}ms) is >3× the p95 SLO. "
                    "Tail latency may indicate GC pauses or lock contention."
                )
            if lm.throughput_rps < 50:
                recs.append(
                    "🟡 Throughput < 50 req/s. Consider adding uvicorn workers "
                    "(--workers N) or horizontal scaling."
                )
        if self.container_restarts > 0:
            recs.append(
                f"🔴 {self.container_restarts} container restart(s) detected. "
                "Check OOM kills, healthcheck failures, or uncaught exceptions."
            )
        # Generic best-practice recommendations
        for p in self.phases:
            if p.name == "lint" and not p.passed:
                recs.append("🟡 Fix lint issues before merging – enforce in CI with --fail-on-error.")
            if p.name == "unit_tests" and not p.passed:
                recs.append("🔴 Unit tests MUST pass. Fix failures before any load testing.")
        if not recs:
            recs.append("✅ All checks passed. System is within SLO bounds.")


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
        f"**Duration**: {report.total_duration_s:.1f}s  ",
        f"**Container restarts**: {report.container_restarts}",
        "",
        "## Phases",
        "",
        "| Phase | Status | Duration | Detail |",
        "|-------|--------|----------|--------|",
    ]
    for p in report.phases:
        status = "✅ PASS" if p.passed else "❌ FAIL"
        dur = f"{p.duration_ms:.0f}ms"
        lines.append(f"| {p.name} | {status} | {dur} | {p.detail} |")

    if report.load_metrics:
        lm = report.load_metrics
        lines += [
            "",
            "## Load Test Metrics",
            "",
            f"| Metric | Value | SLO | Status |",
            f"|--------|-------|-----|--------|",
            f"| Total requests | {lm.total_requests:,} | – | – |",
            f"| Throughput | {lm.throughput_rps:.1f} req/s | – | – |",
            f"| Error rate | {lm.error_rate_pct:.2f}% | < {SLO_ERROR_RATE_PCT}% | {'✅' if lm.slo_error_rate_ok else '❌'} |",
            f"| Read p50 | {lm.read_p50_ms:.0f}ms | – | – |",
            f"| Read p95 | {lm.read_p95_ms:.0f}ms | < {SLO_READ_P95_MS}ms | {'✅' if lm.slo_read_p95_ok else '❌'} |",
            f"| Read p99 | {lm.read_p99_ms:.0f}ms | – | – |",
            f"| Write p50 | {lm.write_p50_ms:.0f}ms | – | – |",
            f"| Write p95 | {lm.write_p95_ms:.0f}ms | < {SLO_WRITE_P95_MS}ms | {'✅' if lm.slo_write_p95_ok else '❌'} |",
            f"| Write p99 | {lm.write_p99_ms:.0f}ms | – | – |",
        ]

    if report.recommendations:
        lines += ["", "## Recommendations", ""]
        for r in report.recommendations:
            lines.append(f"- {r}")

    lines += [
        "",
        "## Artifacts",
        "",
        f"- `{ARTIFACTS_DIR}/report.json`",
        f"- `{ARTIFACTS_DIR}/report.md`",
        f"- `{ARTIFACTS_DIR}/k6-summary.json` (if load test ran)",
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
        console.print(f"\n[bold]Load:[/bold] {lm.total_requests:,} reqs, "
                       f"{lm.throughput_rps:.1f} rps, "
                       f"err={lm.error_rate_pct:.2f}%, "
                       f"read_p95={lm.read_p95_ms:.0f}ms, "
                       f"write_p95={lm.write_p95_ms:.0f}ms")

    if report.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for r in report.recommendations:
            console.print(f"  {r}")

    verdict = "[bold green]✅ OVERALL PASS[/bold green]" if report.overall_pass else "[bold red]❌ OVERALL FAIL[/bold red]"
    console.print(f"\n{verdict}  (duration: {report.total_duration_s:.1f}s)\n")


def _plain_console(report: QAReport) -> None:
    print("\n" + "=" * 60)
    print("  QA REPORT")
    print("=" * 60)
    for p in report.phases:
        icon = "✅" if p.passed else "❌"
        print(f"  {icon} {p.name:<25} {p.duration_ms:>8.0f}ms  {p.detail[:50]}")

    if report.load_metrics:
        lm = report.load_metrics
        print(f"\n  Load: {lm.total_requests:,} reqs, {lm.throughput_rps:.1f} rps, "
              f"err={lm.error_rate_pct:.2f}%, "
              f"read_p95={lm.read_p95_ms:.0f}ms, write_p95={lm.write_p95_ms:.0f}ms")

    if report.recommendations:
        print("\n  Recommendations:")
        for r in report.recommendations:
            print(f"    {r}")

    verdict = "✅ OVERALL PASS" if report.overall_pass else "❌ OVERALL FAIL"
    print(f"\n  {verdict}  (duration: {report.total_duration_s:.1f}s)")
    print("=" * 60 + "\n")


def _to_dict(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in asdict(obj).items()}
    return obj


# ── k6 JSON parser ───────────────────────────────────────────────────

def parse_k6_summary(path: str) -> LoadMetrics | None:
    """Parse k6 JSON summary into LoadMetrics."""
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
    duration_s = _val("iteration_duration", "max") / 1000 if _val("iteration_duration", "max") else 1.0

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
    )

    lm.slo_error_rate_ok = lm.error_rate_pct < SLO_ERROR_RATE_PCT
    lm.slo_read_p95_ok = lm.read_p95_ms < SLO_READ_P95_MS
    lm.slo_write_p95_ok = lm.write_p95_ms < SLO_WRITE_P95_MS

    return lm

