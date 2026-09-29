"""Checks the lock files before a workflow opens and merges its own PR.

Run with the changes still uncommitted: the tool sets are compared with HEAD.
Fails if an install flag is not the expected boolean (a quoted 'false' is a
truthy string to ephemeris), or if a tool that was in a lock file is gone.
"""
import glob
import subprocess
import sys

import yaml

EXPECTED = {
    "install_resolver_dependencies": False,
    "install_tool_dependencies": False,
    "install_repository_dependencies": True,
}


def tool_keys(doc):
    return {(t["name"], t["owner"]) for t in (doc or {}).get("tools", [])}


def committed(path):
    result = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True)
    return yaml.safe_load(result.stdout) if result.returncode == 0 else None


def main():
    errors = []
    for path in sorted(glob.glob("*.yaml.lock")):
        with open(path) as handle:
            doc = yaml.safe_load(handle) or {}
        for key, want in EXPECTED.items():
            if doc.get(key) is not want:
                errors.append(f"{path}: {key}={doc.get(key)!r}, expected {want!r}")
        before = committed(path)
        if before is not None:
            lost = sorted(tool_keys(before) - tool_keys(doc))
            if lost:
                errors.append(f"{path}: {len(lost)} tool(s) removed, e.g. {lost[:3]}")
    if errors:
        sys.exit("\n".join(errors))
    print("lock files OK")


if __name__ == "__main__":
    main()
