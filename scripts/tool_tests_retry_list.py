"""List the tests that failed with infrastructure errors, to retry them one by one.

Writes "tool_id<TAB>tool_version<TAB>test_index" lines and prints how many. Writes
nothing when there are none, or more than --max: that many points at a wider
outage, better retested later with scope failed.
"""

import argparse
import json
from pathlib import Path

from tool_tests_common import classify_test


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, help="ephemeris --test-json output")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max", type=int, default=50)
    args = parser.parse_args()

    results = Path(args.results)
    failed = []
    if results.is_file():
        for test in json.loads(results.read_text()).get("tests", []):
            data = test.get("data") or {}
            if data.get("tool_id") and classify_test(data) == "infra":
                failed.append((data["tool_id"], data.get("tool_version", ""), data.get("test_index", 0)))
    if 0 < len(failed) <= args.max:
        Path(args.out).write_text("".join(f"{t}\t{v}\t{i}\n" for t, v, i in failed))
    print(len(failed))


if __name__ == "__main__":
    main()
