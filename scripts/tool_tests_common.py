"""Classify ephemeris tool test results.

Every failed test gets one of three kinds:

- setup: the test cannot run here, e.g. it selects a reference genome or data
  table entry this server does not have. Says nothing about the tool.
- infra: no job ran because uploading the test data or talking to Galaxy failed
  (HTTP 5xx, staging error, timeout). Worth a retry.
- tool: a job ran and failed, or its outputs did not match.

A tool's status comes from the tool-kind failures only:

- passed: every test that ran passed
- partial: some tests fail, at least one passes
- broken: tests ran and every one of them failed
- infra: only infra failures left after the retry
- untestable: nothing ran (only setup failures or skipped tests)
"""

import re

GUID_RE = re.compile(r"^[^/]+/repos/(?P<owner>[^/]+)/(?P<name>[^/]+)/(?P<tool>[^/]+)(?:/|$)")

SETUP_PATTERNS = re.compile(
    r"an invalid option .* was selected|is not a valid option|no data table|data table .* (?:not found|missing)"
    r"|no entries in data table|not available in data table|parameter .* invalid",
    re.IGNORECASE,
)
INFRA_PATTERNS = re.compile(
    r"input staging problem|staging failed|internal server error|bad gateway|service unavailable|gateway time-?out"
    r"|timed out|timeout|connection (?:reset|refused|aborted)|max retries exceeded|\b50[0234]\b",
    re.IGNORECASE,
)


def classify_test(data):
    """Return 'pass', 'skip', 'setup', 'infra' or 'tool' for one test result."""
    status = data.get("status")
    if status == "success":
        return "pass"
    if status == "skip":
        return "skip"
    problem = data.get("execution_problem") or ""
    job_ran = bool(data.get("job"))
    if data.get("dynamic_param_error") or SETUP_PATTERNS.search(problem):
        return "setup"
    if not job_ran and INFRA_PATTERNS.search(problem):
        return "infra"
    if not job_ran and not data.get("output_problems"):
        # Rejected before a job was created, most often by the test's own parameters.
        return "setup"
    return "tool"


def tool_status(counts):
    if counts["tool"] and counts["pass"]:
        return "partial"
    if counts["tool"]:
        return "broken"
    if counts["infra"]:
        return "infra"
    if counts["pass"]:
        return "passed"
    return "untestable"


def tool_key(tool_id):
    """Tool id without its version, to compare versions of the same tool."""
    match = GUID_RE.match(tool_id)
    if not match:
        return tool_id
    return f"{match['owner']}/{match['name']}/{match['tool']}"


def versioned_id(tool_id, version):
    """Tool Shed tool id with its version; test results give the two separately."""
    if GUID_RE.match(tool_id) and version and not tool_id.endswith(f"/{version}"):
        return f"{tool_id}/{version}"
    return tool_id


def repository_of(tool_id):
    match = GUID_RE.match(tool_id)
    return f"{match['owner']}/{match['name']}" if match else ""
