#!/usr/bin/env python3
"""Before Prime spawns a Planner task, check token budget in 03-token-log.md.
Warn if we're above 80% of any budget share."""
import sys, pathlib
log = pathlib.Path("requirements/03-token-log.md")
if not log.exists():
    sys.exit(0)  # first run
# TODO: parse log, compare against caps, print warning to stderr if >80%
sys.exit(0)
