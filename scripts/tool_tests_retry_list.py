"""Write a tool list of the chunk's repositories that had infrastructure failures.

Prints the number of repositories; writes nothing when there are none.
"""

import argparse
import json
from pathlib import Path

import yaml

from tool_tests_common import classify_test, repository_of


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk", required=True, help="Tool list that was tested")
    parser.add_argument("--results", required=True, help="ephemeris --test-json output")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    results = Path(args.results)
    failed = set()
    if results.is_file():
        for test in json.loads(results.read_text()).get("tests", []):
            data = test.get("data") or {}
            if data.get("tool_id") and classify_test(data) == "infra":
                failed.add(repository_of(data["tool_id"]))

    tools = [r for r in yaml.safe_load(Path(args.chunk).read_text()).get("tools", [])
             if f"{r['owner']}/{r['name']}" in failed]
    if tools:
        Path(args.out).write_text(yaml.safe_dump({"tools": tools}, sort_keys=False))
    print(len(tools))


if __name__ == "__main__":
    main()
