#!/usr/bin/env python3
"""After Developer writes/edits code, automatically nudge Prime to run Tester."""
print("HOOK: development complete — remember to run the Tester sub-agent next.", file=__import__('sys').stderr)
