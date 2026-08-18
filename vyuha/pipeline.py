"""The one function that ties the stages together."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import analyze, clean, detect, ingest, report, schema
from .analyze import Insights
from .clean import CleanTable


@dataclass
class RunResult:
    insights: Insights
    tables: list[CleanTable]
    skipped: list[tuple[str, str]]  # (sheet name, why)
    output: Path | None = None


def run(
    source: str | Path,
    as_of: datetime | None = None,
    min_rows: int = 1,
) -> RunResult:
    """Read ``source``, understand it, clean it and analyse it."""
    source = Path(source)
    sheets = ingest.read_source(source)

    tables: list[CleanTable] = []
    skipped: list[tuple[str, str]] = []

    for sheet in sheets:
        detected = detect.detect(sheet)
        if detected.kind == schema.UNKNOWN:
            recognised = ", ".join(sorted(detected.mapping)) or "nothing"
            skipped.append(
                (sheet.name, f"could not tell what this sheet is (recognised: {recognised})")
            )
            continue
        table = clean.clean(detected)
        if table.rows_out < min_rows:
            skipped.append((sheet.name, "no usable rows after cleaning"))
            continue
        tables.append(table)

    insights = analyze.analyse(tables, source=source.name, as_of=as_of)
    for name, why in skipped:
        insights.warnings.append(f"Skipped sheet '{name}' — {why}.")

    return RunResult(insights=insights, tables=tables, skipped=skipped)


def write_report(result: RunResult, output: str | Path, client: str | None = None) -> Path:
    """Render the dashboard to ``output`` and return the path written."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.render(result.insights, client=client), encoding="utf-8")
    result.output = output
    return output
