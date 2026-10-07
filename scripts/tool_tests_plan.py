"""Pick the installed repository revisions to test and split them into chunks.

Reads the installed tool list (get-tool-list output) and the current test status,
writes one ephemeris tool list per chunk, and prints the chunk names as a JSON
list for the workflow matrix.

scope=new: revisions that have no entry in the status file yet. Without a status
file, every installed revision is recorded as a baseline and nothing is tested.
scope=all: every installed repository, latest revision only unless --all-revisions.
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_status(path):
    if path and Path(path).is_file():
        return json.loads(Path(path).read_text())
    return None


def installed_revisions(installed, all_revisions):
    """Yield (tool_shed_url, owner, name, revision) for each installed revision.

    get-tool-list lists revisions oldest first, so the last one is the newest.
    """
    for repo in installed.get("tools", []):
        revisions = repo.get("revisions") or []
        if not all_revisions:
            revisions = revisions[-1:]
        for revision in revisions:
            yield repo.get("tool_shed_url", "toolshed.g2.bx.psu.edu"), repo["owner"], repo["name"], revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", required=True, help="get-tool-list output")
    parser.add_argument("--status", help="Current status.json, if any")
    parser.add_argument("--scope", choices=["new", "all"], default="new")
    parser.add_argument("--all-revisions", action="store_true", help="scope=all: test every installed revision")
    parser.add_argument("--chunk-size", type=int, default=25, help="Repository revisions per chunk")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--baseline-out", help="Write a baseline status file here when there is none yet")
    args = parser.parse_args()

    installed = yaml.safe_load(Path(args.installed).read_text())
    status = load_status(args.status)
    known = status.get("repositories", {}) if status else {}

    if args.scope == "new" and status is None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        baseline = {"repositories": {}, "tools": {}}
        for shed, owner, name, revision in installed_revisions(installed, all_revisions=True):
            baseline["repositories"].setdefault(f"{owner}/{name}", {})[revision] = {"baseline_at": now}
        if args.baseline_out:
            Path(args.baseline_out).write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n")
        logger.info("No status file yet: recorded %d repositories as baseline, testing nothing", len(baseline["repositories"]))
        print(json.dumps([]))
        return

    selected = {}
    for shed, owner, name, revision in installed_revisions(installed, all_revisions=args.scope == "new" or args.all_revisions):
        if args.scope == "new" and revision in known.get(f"{owner}/{name}", {}):
            continue
        revisions = selected.setdefault((shed, owner, name), [])
        # A repository can be listed once per tool panel section.
        if revision not in revisions:
            revisions.append(revision)

    pairs = [(key, rev) for key, revs in sorted(selected.items()) for rev in revs]
    logger.info("Selected %d revisions from %d repositories", len(pairs), len(selected))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for start in range(0, len(pairs), args.chunk_size):
        tools = {}
        for (shed, owner, name), rev in pairs[start:start + args.chunk_size]:
            entry = tools.setdefault((shed, owner, name), {"name": name, "owner": owner, "tool_shed_url": shed, "revisions": []})
            entry["revisions"].append(rev)
        chunk = f"chunk-{len(chunks):03d}"
        (out_dir / f"{chunk}.yaml").write_text(yaml.safe_dump({"tools": list(tools.values())}, sort_keys=False))
        chunks.append(chunk)
    print(json.dumps(chunks))


if __name__ == "__main__":
    main()
