"""Purge the test user's histories whose name starts with a prefix."""

import argparse
import logging
import os

from bioblend.galaxy import GalaxyInstance

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--galaxy", required=True)
    parser.add_argument("--prefix", required=True, help="History name prefix, e.g. tool-tests-<run id>")
    args = parser.parse_args()

    gi = GalaxyInstance(args.galaxy, key=os.environ["GALAXY_TEST_API_TOKEN"])
    for history in gi.histories.get_histories():
        if history["name"].startswith(args.prefix):
            gi.histories.delete_history(history["id"], purge=True)
            logger.info("Purged history %s (%s)", history["name"], history["id"])


if __name__ == "__main__":
    main()
