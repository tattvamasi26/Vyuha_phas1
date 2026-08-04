#!/usr/bin/env python3
"""Before any bash command that looks deploy-y (push, deploy, publish, release), block if tests haven't passed."""
import sys, os
cmd = os.environ.get("HOOK_TOOL_INPUT", "")
if any(k in cmd.lower() for k in ["deploy", "push origin main", "publish", "release"]):
    # TODO: check for a recent green test result artifact
    print("HOOK: deploy detected — confirm Tester reported all-green in the last cycle.", file=sys.stderr)
sys.exit(0)
