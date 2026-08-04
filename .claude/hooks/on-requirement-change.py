#!/usr/bin/env python3
"""When any file in requirements/ changes, nudge Prime to summarize the delta for Vishu."""
print("HOOK: requirements/ changed — summarize the delta for Vishu before proceeding.", file=__import__('sys').stderr)
