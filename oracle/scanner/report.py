import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from oracle.scanner.models import ScanRow
from oracle.scanner.t2_models import EvRow


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _safe_segment(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


@dataclass(frozen=True)
class ScanReport:
    league: str
    snapshot_ts: datetime
    rule_version: str
    rows: list[ScanRow]
    ev_rows: list[EvRow] = field(default_factory=list)

    def auto_rows(self) -> list[ScanRow]:
        return [r for r in self.rows if r.pricing_mode == "auto"]

    def verify_rows(self) -> list[ScanRow]:
        return [r for r in self.rows if r.pricing_mode == "verify"]

    def _header(self) -> str:
        return (
            f"Oracle Tier-1 Scan — league={self.league} "
            f"snapshot={self.snapshot_ts.isoformat()} rules={self.rule_version}"
        )

    def to_terminal(self) -> str:
        lines = [self._header(), ""]
        lines.append("== AUTO-PRICED ==")
        lines.append(
            f"{'transform':<32}{'margin':>10}{'margin%':>10}{'liq':>8}{'conf':>7}{'demand':>9}"
        )
        for r in self.auto_rows():
            pct = "—" if r.margin_pct is None else f"{r.margin_pct * 100:.0f}%"
            demand = "⚠ thin" if r.demand == "thin" else r.demand
            lines.append(
                f"{r.name[:32]:<32}{_fmt(r.margin):>10}{pct:>10}"
                f"{r.liquidity:>8.0f}{r.confidence:>7.2f}{demand:>9}"
            )
        lines.append("")
        lines.append("== VERIFY-REQUIRED (provisional; click to price) ==")
        for r in self.verify_rows():
            lines.append(f"{r.name[:32]:<32}  input≈{_fmt(r.input_cost)}c  {r.deep_link or ''}")
        lines.append("")
        lines.append("== PROBABILISTIC (Tier-2) ==")
        lines.append(f"{'gamble':<32}{'ev_net':>10}{'stddev':>10}{'conf':>7}")
        for e in self.ev_rows:
            link = e.deep_link or "—"
            lines.append(
                f"{e.name[:32]:<32}{e.ev_net:>10.2f}{e.stddev:>10.2f}{e.confidence:>7.2f}  {link}"
            )
            if e.bankroll_note:
                lines.append(f"    {e.bankroll_note}")
            if e.unresolved_outcomes:
                lines.append(f"    ! {e.unresolved_outcomes} outcome(s) unpriced (excluded)")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            f"# Oracle Tier-1 Scan — {self.league}",
            "",
            f"- League: `{self.league}`",
            f"- Snapshot: `{self.snapshot_ts.isoformat()}`",
            f"- Transforms rule version: `{self.rule_version}`",
            "",
            "## AUTO-PRICED",
            "",
            "| Transform | Margin (c) | Margin % | Liquidity | Confidence | Demand | Source |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
        for r in self.auto_rows():
            pct = "—" if r.margin_pct is None else f"{r.margin_pct * 100:.0f}%"
            lines.append(
                f"| {r.name} | {_fmt(r.margin)} | {pct} | "
                f"{r.liquidity:.0f} | {r.confidence:.2f} | {r.demand} | {r.source} |"
            )
        lines += [
            "",
            "## VERIFY-REQUIRED (provisional — click deep-link to price)",
            "",
            "| Transform | Input cost (c) | Deep-link | Source |",
            "|---|---:|---|---|",
        ]
        for r in self.verify_rows():
            link = f"[open]({r.deep_link})" if r.deep_link else "—"
            lines.append(f"| {r.name} | {_fmt(r.input_cost)} | {link} | {r.source} |")
        lines += [
            "",
            "## PROBABILISTIC (Tier-2)",
            "",
            "| Gamble | EV gross (c) | EV net (c) | Stddev | Liquidity | Confidence | Bankroll | Deep-link |",  # noqa: E501
            "|---|---:|---:|---:|---:|---:|---|---|",
        ]
        for e in self.ev_rows:
            link = f"[open]({e.deep_link})" if e.deep_link else "—"
            lines.append(
                f"| {e.name} | {e.ev_gross:.2f} | {e.ev_net:.2f} | {e.stddev:.2f} | "
                f"{e.liquidity:.0f} | {e.confidence:.2f} | {e.bankroll_note or '—'} | {link} |"
            )
        return "\n".join(lines) + "\n"

    def to_json(self) -> str:
        payload = {
            "league": self.league,
            "snapshot_ts": self.snapshot_ts.isoformat(),
            "rule_version": self.rule_version,
            "rows": [json.loads(r.model_dump_json()) for r in self.rows],
            "ev_rows": [json.loads(e.model_dump_json()) for e in self.ev_rows],
        }
        return json.dumps(payload, indent=2)


def write_report(report: ScanReport, reports_dir: Path) -> tuple[Path, Path]:
    league_dir = reports_dir / _safe_segment(report.league)
    league_dir.mkdir(parents=True, exist_ok=True)
    stem = report.snapshot_ts.strftime("%Y-%m-%d-%H%M")
    md_path = league_dir / f"{stem}.md"
    json_path = league_dir / f"{stem}.json"
    md_path.write_text(report.to_markdown())
    json_path.write_text(report.to_json())
    return md_path, json_path
