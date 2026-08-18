"""Command line entry point.

    vyuha run  <file.xlsx> [-o dashboard.html] [--client "Name"] [--open]
    vyuha check <file.xlsx>          # what did we understand, without a report
    vyuha demo  [-o out/]            # build a messy sample file and its dashboard
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import pipeline, sample, schema
from .analyze import CRITICAL, WARNING
from .ingest import IngestError

DEFAULT_OUT = Path("out")

SEVERITY_MARK = {CRITICAL: "!!", WARNING: " !"}

# The Windows console is still cp1252 by default, which cannot encode ₹.
# Alert text is shared with the HTML report, so transliterate on the way out
# rather than weakening the report.
_FALLBACKS = {"₹": "Rs.", "→": "->", "—": "-", "–": "-", "×": "x", "&rarr;": "->"}


def say(text: str = "", stream=None) -> None:
    stream = stream or sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        for char, replacement in _FALLBACKS.items():
            text = text.replace(char, replacement)
        text = text.encode(encoding, errors="replace").decode(encoding)
    print(text, file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vyuha",
        description="Turn a distributor's Excel file into a business dashboard.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="analyse a file and write the dashboard")
    run_cmd.add_argument("file", help="path to .xlsx / .xls / .csv")
    run_cmd.add_argument("-o", "--output", help="output .html path")
    run_cmd.add_argument("--client", help="client name to show on the dashboard")
    run_cmd.add_argument("--as-of", help="treat this date as today (YYYY-MM-DD)")
    run_cmd.add_argument("--open", action="store_true", dest="open_after",
                         help="open the dashboard in a browser when done")

    check_cmd = sub.add_parser("check", help="show what Vyuha understood, no report")
    check_cmd.add_argument("file")
    check_cmd.add_argument("--as-of", help="treat this date as today (YYYY-MM-DD)")

    demo_cmd = sub.add_parser("demo", help="generate a messy sample file and its dashboard")
    demo_cmd.add_argument("-o", "--output-dir", default=str(DEFAULT_OUT))
    demo_cmd.add_argument("--open", action="store_true", dest="open_after")

    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            return _run(args)
        if args.command == "check":
            return _check(args)
        if args.command == "demo":
            return _demo(args)
    except IngestError as exc:
        say(f"error: {exc}", stream=sys.stderr)
        return 2
    return 1


# --- commands -------------------------------------------------------------


def _run(args) -> int:
    source = Path(args.file)
    output = Path(args.output) if args.output else DEFAULT_OUT / f"{source.stem}-dashboard.html"

    result = pipeline.run(source, as_of=_as_of(args))
    _print_understanding(result)

    if not result.tables:
        say("\nNothing usable was found — no dashboard written.", stream=sys.stderr)
        return 3

    path = pipeline.write_report(result, output, client=args.client)
    _print_alerts(result)
    say(f"\nDashboard written to {path}")
    if args.open_after:
        webbrowser.open(path.resolve().as_uri())
    return 0


def _check(args) -> int:
    result = pipeline.run(args.file, as_of=_as_of(args))
    _print_understanding(result, verbose=True)
    _print_alerts(result)
    return 0 if result.tables else 3


def _demo(args) -> int:
    out_dir = Path(args.output_dir)
    workbook = sample.build(out_dir / "sample-distributor.xlsx")
    say(f"Sample workbook written to {workbook}")

    result = pipeline.run(workbook)
    _print_understanding(result)
    path = pipeline.write_report(result, out_dir / "sample-dashboard.html",
                                 client="Shree Balaji Distributors")
    _print_alerts(result)
    say(f"\nDashboard written to {path}")
    if args.open_after:
        webbrowser.open(path.resolve().as_uri())
    return 0


# --- output ---------------------------------------------------------------


def _print_understanding(result: pipeline.RunResult, verbose: bool = False) -> None:
    say(f"\nRead {result.insights.source}")
    for table in result.tables:
        fields = ", ".join(
            schema.LABELS.get(c, c) for c in table.frame.columns if c in schema.LABELS
        )
        say(
            f"  [{schema.TABLE_LABELS.get(table.kind, table.kind):<12}] "
            f"{table.sheet:<20} header on row {table.header_row}, "
            f"{table.rows_out} rows"
            + (f" ({table.rows_dropped} dropped)" if table.rows_dropped else "")
        )
        say(f"{'':17}understood: {fields}")
        if verbose and table.unmapped:
            say(f"{'':17}ignored columns: {', '.join(table.unmapped)}")
        for issue in table.issues:
            say(f"{'':17}- {issue}")

    for name, why in result.skipped:
        say(f"  [skipped     ] {name:<20} {why}")


def _print_alerts(result: pipeline.RunResult) -> None:
    alerts = result.insights.alerts
    if not alerts:
        say("\nNo alerts — nothing urgent in this file.")
        return
    say(f"\n{len(alerts)} alert(s):")
    for alert in alerts:
        mark = SEVERITY_MARK.get(alert.severity, "  ")
        say(f" {mark} {alert.title}")
        say(f"      {alert.detail}")


def _as_of(args) -> datetime | None:
    raw = getattr(args, "as_of", None)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"error: --as-of must be YYYY-MM-DD, got '{raw}'")


if __name__ == "__main__":
    raise SystemExit(main())
