"""Vyuha — turn a distributor's messy Excel file into a business dashboard.

    from vyuha import run, write_report
    result = run("sales.xlsx")
    write_report(result, "dashboard.html")
"""

from .analyze import Alert, Insights
from .clean import CleanTable
from .pipeline import RunResult, run, write_report

__version__ = "0.1.0"

__all__ = [
    "Alert",
    "CleanTable",
    "Insights",
    "RunResult",
    "run",
    "write_report",
    "__version__",
]
