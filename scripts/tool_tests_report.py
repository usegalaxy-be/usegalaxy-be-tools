"""Merge ephemeris test results into the tool test status file.

One entry per tool id (the full guid, so per version). See tool_tests_common for
how failures are classified. A tool is potentially_broken when it is broken
(every test that ran failed) or has a regression (it fails while a newer or older
version of the same tool passes), and it is not listed in
tool-tests/expected-failures.yaml.

Results files whose name contains "retry" are applied last and replace the first
attempt of the same test.
"""

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from tool_tests_common import classify_test, repository_of, tool_key, tool_status, versioned_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HISTORY_LENGTH = 10
FAILING = ("broken", "partial", "infra")


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


def version_key(version):
    return [(0, int(p)) if p.isdigit() else (1, p) for p in re.findall(r"\d+|[a-z]+", str(version).lower())]


def load_results(results_dir):
    """Test results by test id, retry files overriding first attempts."""
    files = sorted(Path(results_dir).glob("**/*.json"), key=lambda p: ("retry" in p.name, p.name))
    tests = {}
    for result_file in files:
        for test in json.loads(result_file.read_text()).get("tests", []):
            if test.get("data", {}).get("tool_id"):
                tests[test["id"]] = test["data"]
    return tests


def apply_flags(tools, expected):
    """Set regression, expected_failure and potentially_broken on every tool."""
    by_key = {}
    for tool_id, tool in tools.items():
        by_key.setdefault(tool.get("tool", tool_key(tool_id)), []).append((tool_id, tool))
    for versions in by_key.values():
        for tool_id, tool in versions:
            tool["regression"] = False
            tool["regression_from"] = ""
            if tool["status"] not in ("broken", "partial"):
                continue
            older_passing = [t["version"] for tid, t in versions
                             if tid != tool_id and t["status"] == "passed"
                             and version_key(t["version"]) < version_key(tool["version"])]
            if older_passing:
                tool["regression"] = True
                tool["regression_from"] = max(older_passing, key=version_key)
    for tool_id, tool in tools.items():
        reason = expected_reason(tool_id, expected)
        tool["expected_failure"] = reason is not None
        tool["expected_reason"] = reason or ""
        tool["potentially_broken"] = (tool["status"] == "broken" or tool["regression"]) and reason is None


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
    # Entries from before the failure classification have no history; they are retested on the next run.
    status["tools"] = {tid: t for tid, t in status["tools"].items() if "history" in t}
    expected = load_expected(args.expected)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    previous = {tid: (t["potentially_broken"], t["status"]) for tid, t in status["tools"].items()}

    for chunk in sorted(Path(args.chunks_dir).glob("*.yaml")):
        for repo in yaml.safe_load(chunk.read_text()).get("tools", []):
            for revision in repo.get("revisions", []):
                status["repositories"].setdefault(f"{repo['owner']}/{repo['name']}", {})[revision] = {
                    "tested_at": now, "run": args.run_url}

    counts = {}
    for data in load_results(args.results_dir).values():
        entry = counts.setdefault(versioned_id(data["tool_id"], data.get("tool_version", "")), {"version": data.get("tool_version", ""),
                                                    "tests": dict.fromkeys(("pass", "tool", "setup", "infra", "skip"), 0)})
        entry["tests"][classify_test(data)] += 1

    for tool_id, entry in counts.items():
        state = tool_status(entry["tests"])
        old = status["tools"].get(tool_id, {})
        history = ([{"at": now, "status": state}] + old.get("history", []))[:HISTORY_LENGTH]
        status["tools"][tool_id] = {
            "repository": repository_of(tool_id),
            "tool": tool_key(tool_id),
            "version": entry["version"],
            "tests": entry["tests"],
            "status": state,
            "tested_at": now,
            "run": args.run_url,
            "history": history,
            "runs": old.get("runs", 0) + 1,
            "failed_runs": old.get("failed_runs", 0) + (state in FAILING),
        }

    apply_flags(status["tools"], expected)

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
    tested = [tid for tid in counts if tid in tools]
    newly_broken = [tid for tid in tested if tools[tid]["potentially_broken"] and not previous.get(tid, (False,))[0]]
    fixed = [tid for tid in tested if previous.get(tid, (False,))[0] and not tools[tid]["potentially_broken"]]
    infra = [tid for tid in tested if tools[tid]["status"] == "infra"]
    states = {}
    for tool in tools.values():
        states[tool["status"]] = states.get(tool["status"], 0) + 1
    lines = [
        "## Tool tests",
        "",
        f"Tested in this run: {len(tested)} tools. Overall: {len(tools)} tools, "
        + ", ".join(f"{n} {s}" for s, n in sorted(states.items()))
        + f"; {sum(t['potentially_broken'] for t in tools.values())} potentially broken.",
        "",
    ]
    for title, items in (("Newly potentially broken", newly_broken), ("Fixed", fixed),
                         ("Infrastructure errors after retry", infra)):
        if items:
            lines += [f"### {title}", ""]
            for tid in sorted(items):
                t = tools[tid]
                note = f" (regression, passes in {t['regression_from']})" if t["regression"] else ""
                lines.append(f"- `{tid}`: {t['status']}{note}")
            lines.append("")
    if args.summary:
        with open(args.summary, "a") as fh:
            fh.write("\n".join(lines) + "\n")
    logger.info("%d tools tested, %d newly potentially broken", len(tested), len(newly_broken))


if __name__ == "__main__":
    main()
