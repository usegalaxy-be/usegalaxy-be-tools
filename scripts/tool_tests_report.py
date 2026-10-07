"""Merge ephemeris test results into the tool test status file.

One entry per tool id (the full guid, so per version) with its test counts and a
status. A tool with failing or erroring tests that is not listed in
tool-tests/expected-failures.yaml is marked potentially_broken.
"""

import argparse
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

GUID_RE = re.compile(r"^[^/]+/repos/(?P<owner>[^/]+)/(?P<name>[^/]+)/")


def load_expected(path):
    if not path or not Path(path).is_file():
        return []
    entries = yaml.safe_load(Path(path).read_text()) or []
    return [(re.compile(e["tool_id"]), e.get("reason", "")) for e in entries]


def expected_reason(tool_id, expected):
    for pattern, reason in expected:
        if pattern.match(tool_id):
            return reason
    return None


def tool_status(counts):
    if counts["failure"] or counts["error"]:
        return "failed"
    if counts["success"]:
        return "passed"
    return "skipped"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", required=True, help="status.json to update in place (created if missing)")
    parser.add_argument("--chunks-dir", required=True, help="Chunk tool lists that were tested")
    parser.add_argument("--results-dir", required=True, help="ephemeris --test-json outputs")
    parser.add_argument("--expected", help="expected-failures.yaml")
    parser.add_argument("--installed", help="get-tool-list output; drops tools of repositories no longer installed")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--summary", help="Write a Markdown summary here")
    args = parser.parse_args()

    status_path = Path(args.status)
    status = json.loads(status_path.read_text()) if status_path.is_file() else {"repositories": {}, "tools": {}}
    expected = load_expected(args.expected)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    previous = {tid: t.get("potentially_broken", False) for tid, t in status["tools"].items()}

    for chunk in sorted(Path(args.chunks_dir).glob("*.yaml")):
        for repo in yaml.safe_load(chunk.read_text()).get("tools", []):
            for revision in repo.get("revisions", []):
                status["repositories"].setdefault(f"{repo['owner']}/{repo['name']}", {})[revision] = {
                    "tested_at": now, "run": args.run_url}

    counts = {}
    for result_file in sorted(Path(args.results_dir).glob("**/*.json")):
        for test in json.loads(result_file.read_text()).get("tests", []):
            data = test.get("data") or {}
            tool_id = data.get("tool_id")
            if not tool_id:
                continue
            entry = counts.setdefault(tool_id, {"version": data.get("tool_version", ""), "tests": Counter()})
            entry["tests"][data.get("status", "error")] += 1

    for tool_id, entry in counts.items():
        tests = {k: entry["tests"].get(k, 0) for k in ("success", "failure", "error", "skip")}
        state = tool_status(tests)
        reason = expected_reason(tool_id, expected)
        match = GUID_RE.match(tool_id)
        status["tools"][tool_id] = {
            "repository": f"{match['owner']}/{match['name']}" if match else "",
            "version": entry["version"],
            "tests": tests,
            "status": state,
            "expected_failure": reason is not None,
            "expected_reason": reason or "",
            "potentially_broken": state == "failed" and reason is None,
            "tested_at": now,
            "run": args.run_url,
        }

    # Re-apply the expected list to tools not tested in this run, so edits to it take effect.
    for tool_id, tool in status["tools"].items():
        reason = expected_reason(tool_id, expected)
        tool["expected_failure"] = reason is not None
        tool["expected_reason"] = reason or ""
        tool["potentially_broken"] = tool["status"] == "failed" and reason is None

    if args.installed:
        installed = {f"{r['owner']}/{r['name']}" for r in yaml.safe_load(Path(args.installed).read_text()).get("tools", [])}
        gone = [tid for tid, t in status["tools"].items() if t["repository"] and t["repository"] not in installed]
        for tid in gone:
            del status["tools"][tid]
        for repo in [r for r in status["repositories"] if r not in installed]:
            del status["repositories"][repo]
        if gone:
            logger.info("Dropped %d tools of repositories no longer installed", len(gone))

    status["updated_at"] = now
    status_path.write_text(json.dumps(status, indent=1, sort_keys=True) + "\n")

    tools = status["tools"]
    broken = sorted(tid for tid, t in tools.items() if t["potentially_broken"])
    new_broken = [tid for tid in broken if tid in counts and not previous.get(tid, False)]
    fixed = [tid for tid in counts if previous.get(tid) and not tools[tid]["potentially_broken"]]
    unexpected_pass = [tid for tid in counts if tools[tid]["expected_failure"] and tools[tid]["status"] == "passed"]
    lines = [
        "## Tool tests",
        "",
        f"Tested in this run: {len(counts)} tools. Overall: {len(tools)} tools, "
        f"{sum(t['status'] == 'passed' for t in tools.values())} passed, "
        f"{len(broken)} potentially broken, {sum(t['expected_failure'] for t in tools.values())} expected failures.",
        "",
    ]
    for title, items in (("Newly potentially broken", new_broken), ("Fixed", fixed),
                         ("Expected failures that now pass", unexpected_pass)):
        if items:
            lines += [f"### {title}", ""] + [f"- `{tid}`" for tid in sorted(items)] + [""]
    if args.summary:
        with open(args.summary, "a") as fh:
            fh.write("\n".join(lines) + "\n")
    logger.info("%d tools tested, %d newly potentially broken", len(counts), len(new_broken))


if __name__ == "__main__":
    main()
