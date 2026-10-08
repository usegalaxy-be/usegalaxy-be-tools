"""Pick the installed repository revisions to test and split them into chunks.

Reads the installed tool list (get-tool-list output) and the current test status,
writes one ephemeris tool list per chunk, and prints the chunk names as a JSON
list for the workflow matrix.

scope=new: revisions that have no entry in the status file yet. Without a status
file, every installed revision is recorded as a baseline and nothing is tested.
scope=untested: like all, but only revisions without a test result yet, so a
full sweep can be stopped and continued later.
scope=failed: repositories with a tool whose latest result is broken, partial or infra.
scope=flaky: repositories with a tool that failed in at least --flaky-min of its
last runs.
scope=all: every installed repository, its newest revision only unless --all-revisions.
--repositories limits any scope to the given owner/name repositories.
"""

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bioblend import toolshed

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_status(path):
    if path and Path(path).is_file():
        return json.loads(Path(path).read_text())
    return None


def revision_order(shed, owner, name):
    """Position of each installable revision in the Tool Shed, oldest first."""
    for attempt in range(3):
        try:
            revisions = toolshed.ToolShedInstance(url=f"https://{shed}").repositories.get_ordered_installable_revisions(name, owner)
            return {rev: i for i, rev in enumerate(revisions)}
        except Exception as e:  # noqa: BLE001
            logger.warning("Revision order for %s/%s failed (%s), attempt %d", owner, name, e, attempt + 1)
            time.sleep(2 * (attempt + 1))
    return {}


def installed_revisions(installed, all_revisions, only=()):
    """Yield (tool_shed_url, owner, name, revision) for each installed revision.

    A repository can be listed once per tool panel section, each time with some of
    its revisions in no particular order. Without all_revisions only the newest
    one is yielded, by the Tool Shed's order.
    """
    repos = {}
    for repo in installed.get("tools", []):
        if only and f"{repo['owner']}/{repo['name']}" not in only:
            continue
        key = (repo.get("tool_shed_url", "toolshed.g2.bx.psu.edu"), repo["owner"], repo["name"])
        revisions = repos.setdefault(key, [])
        revisions += [r for r in repo.get("revisions") or [] if r not in revisions]
    if not all_revisions:
        with ThreadPoolExecutor(max_workers=8) as pool:
            orders = dict(zip(repos, pool.map(lambda k: revision_order(*k), repos)))
        repos = {key: [max(revs, key=lambda r: orders[key].get(r, -1))] for key, revs in repos.items() if revs}
    for (shed, owner, name), revisions in repos.items():
        for revision in revisions:
            yield shed, owner, name, revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", required=True, help="get-tool-list output")
    parser.add_argument("--status", help="Current status.json, if any")
    parser.add_argument("--scope", choices=["new", "untested", "failed", "flaky", "all"], default="new")
    parser.add_argument("--flaky-min", type=int, default=2, help="scope=flaky: failed runs out of the last 10")
    parser.add_argument("--all-revisions", action="store_true", help="scope=all: test every installed revision")
    parser.add_argument("--repositories", default="", help="Comma-separated owner/name list to limit the run to")
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

    only = {r.strip() for r in args.repositories.split(",") if r.strip()}
    retest = None
    if args.scope in ("failed", "flaky"):
        retest = set()
        for tool in (status or {}).get("tools", {}).values():
            failing = [h for h in tool.get("history", []) if h["status"] in ("broken", "partial", "infra")]
            if (args.scope == "failed" and tool.get("status") in ("broken", "partial", "infra")) or \
               (args.scope == "flaky" and len(failing) >= args.flaky_min):
                retest.add(tool["repository"])
    selected = {}
    for shed, owner, name, revision in installed_revisions(
            installed, all_revisions=args.scope in ("new", "failed", "flaky") or args.all_revisions, only=only):
        repo = f"{owner}/{name}"
        tested = known.get(repo, {}).get(revision, {})
        if only and repo not in only:
            continue
        if args.scope == "new" and revision in known.get(repo, {}):
            continue
        if args.scope == "untested" and "tested_at" in tested:
            continue
        # Retest the revisions that produced the failing results.
        if retest is not None and (repo not in retest or "tested_at" not in tested):
            continue
        selected.setdefault((shed, owner, name), []).append(revision)

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
