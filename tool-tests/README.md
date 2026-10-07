# Tool tests

`.github/workflows/tool-tests.yml` runs the tool tests of installed tools on usegalaxy.be.

- After every run of the install workflow it tests the repository revisions that have no result yet.
- A full sweep is started by hand: Actions > Tool tests > Run workflow, scope `all`.
  It tests the latest revision of every repository, or every installed revision with `all_revisions`.

Tests run as a separate Galaxy user (secret `SECRET_API_TOKEN_TOOL_TESTS`), so they do not share
the job limit of `tool_admin`. Each test job purges its history afterwards.

Results are written to `tool-tests/status.json` on the `tool-test-results` branch, one entry per
tool version. A tool is `potentially_broken` when a test fails or errors and it is not listed in
`expected-failures.yaml`. The usegalaxy.be Grafana "Tool Tests" dashboard reads this file.

The first run without a status file only records the installed revisions as a baseline.
