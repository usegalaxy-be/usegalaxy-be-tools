import argparse
import logging
import time
from pathlib import Path

import yaml
from bioblend import toolshed

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def retry_with_backoff(func, *args, **kwargs):
    backoff = 2
    max_retries = 5

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            if any(
                code in error_msg
                for code in ["429", "502", "503", "504", "timed out", "timeout", "Connection"]
            ):
                if attempt < max_retries - 1:
                    wait_time = 5 if "429" in error_msg else backoff
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed: {error_msg}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    backoff = min(backoff * 2, 60)
                    continue
            raise e
    raise Exception("Retry failed after max attempts")


def backfill(lockfile_name, toolshed_url):
    ts = toolshed.ToolShedInstance(url=toolshed_url)
    lockfile_path = Path(lockfile_name)
    with open(lockfile_path) as f:
        lockfile = yaml.safe_load(f) or {}
    locked_tools = lockfile.get("tools", [])
    total = len(locked_tools)

    logger.info(f"Processing {total} tools from {lockfile_path.name}...")
    changed, skipped, added_total = 0, 0, 0

    for i, tool in enumerate(locked_tools):
        if i % 10 == 0:
            logger.info(
                f"Progress: {i}/{total} tools ({skipped} skipped, {changed} changed, {added_total} revisions added)"
            )

        if i > 0 and i % 50 == 0:
            time.sleep(1)

        name, owner = tool.get("name"), tool.get("owner")
        current_revisions = set(tool.get("revisions", []))

        try:
            installable_list = retry_with_backoff(
                ts.repositories.get_ordered_installable_revisions, name, owner
            )
        except Exception as e:
            logger.warning(f"{name},{owner}: could not get installable revisions ({e})")
            continue

        missing = [r for r in installable_list if r not in current_revisions]
        if not missing:
            skipped += 1
            continue

        logger.info(f"{name},{owner}: adding {len(missing)} missing revision(s): {missing}")
        tool["revisions"] = sorted(current_revisions | set(missing))
        changed += 1
        added_total += len(missing)

    logger.info(
        f"Completed: {total} tools processed, {skipped} unchanged, {changed} changed, "
        f"{added_total} revisions added"
    )

    with open(lockfile_path, "w") as f:
        yaml.dump(lockfile, f, sort_keys=False, default_flow_style=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add every toolshed-installable revision missing from a .yaml.lock file. "
        "Complement to fix_outdated.py, which removes revisions that are no longer installable; "
        "this adds ones that were never captured because update-tool.py only ever records the "
        "single latest revision per run."
    )
    parser.add_argument("lockfile", help="Tool.yaml.lock file path")
    parser.add_argument(
        "--toolshed", default="https://toolshed.g2.bx.psu.edu", help="Toolshed base URL"
    )
    args = parser.parse_args()

    backfill(args.lockfile, args.toolshed)
