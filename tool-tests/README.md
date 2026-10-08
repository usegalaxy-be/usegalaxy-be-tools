# Tool tests

`.github/workflows/tool-tests.yml` runs the tool tests of installed tools on usegalaxy.be.

- After every run of the install workflow it tests the repository revisions that have no result yet.
- A full sweep is started by hand: Actions > Tool tests > Run workflow, scope `all`.
  It tests the latest revision of every repository, or every installed revision with `all_revisions`.
- To (re)test specific repositories, run it with scope `all` and `repositories`, e.g. `iuc/bedtools`.
- Scope `untested` tests only revisions without a result yet: a sweep that is cancelled can be continued later.
- Scopes `failed` and `flaky` retest repositories whose latest result failed, or that failed in at least
  `flaky_min` of their last 10 runs.

Failed tests are classified (see `scripts/tool_tests_common.py`): setup problems (the test needs data this
server does not have) are ignored, infrastructure errors (upload or HTTP errors, no job ran) are retried
once, test by test (skipped when there are more than 50: rerun with scope `failed`), and the rest
count as tool failures. A tool is `partial` when some tests fail and `broken` when all
tests that ran failed. It is `potentially_broken` when its latest tested version is broken, or fails while an
older version of the same tool passes (a regression). An older version that fails while
the latest passes is marked `old_version_broken` instead: still reachable from workflows
that pin it, but a candidate to hide rather than to fix.

Tests run as a separate Galaxy user (secret `SECRET_API_TOKEN_TOOL_TESTS`), so they do not share
the job limit of `tool_admin`. Each test job purges its history afterwards.

Results are written to `tool-tests/status.json` on the `tool-test-results` branch, one entry per
tool version. Tools listed in `expected-failures.yaml` are never marked `potentially_broken`. The usegalaxy.be Grafana "Tool Tests" dashboard reads this file.

The first run without a status file only records the installed revisions as a baseline.
