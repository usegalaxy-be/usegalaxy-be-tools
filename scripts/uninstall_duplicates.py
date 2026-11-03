"""Uninstalls repository revisions that are exact duplicates of another installed revision.

Run on the Galaxy server, as a user that can run gxadmin. A revision is only
uninstalled when all of these hold:

- its status is Installed and it provides at least one tool
- the Tool Shed no longer lists it as installable
- an installed, installable revision of the same repository provides every one
  of its tool versions, so no tool version disappears from Galaxy
- no other installed repository depends on it
- none of its tool versions ever ran a job (unless --allow-jobs)

plan:  writes the decision for every candidate to a TSV file, changes nothing.
apply: re-checks each planned revision, then uninstalls it through the Galaxy API.
       Dry run unless --yes is given.
"""
import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
import time

import requests

TOOL_SHED = "https://toolshed.g2.bx.psu.edu"
INSTALL_DB = "/srv/galaxy/shared/database/shed_data/shed_database/universe.sqlite"
FIELDS = ["owner", "name", "revision", "decision", "reason", "replacement", "jobs", "tool_versions"]


def get(url, params=None):
    # The Tool Shed answers bursts with 429; retry instead of failing the run.
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code not in (429, 502, 503, 504):
            r.raise_for_status()
        time.sleep(10 * (attempt + 1))
    r.raise_for_status()


def installed_revisions(db_path):
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = db.execute(
        "select owner, name, changeset_revision, status, metadata from tool_shed_repository "
        "where not deleted and not uninstalled"
    )
    revisions = []
    for owner, name, rev, status, metadata in rows:
        meta = json.loads(metadata) if metadata else {}
        deps = (meta.get("repository_dependencies") or {}).get("repository_dependencies", [])
        revisions.append({
            "owner": owner, "name": name, "revision": rev, "status": status,
            "tools": {t["guid"] for t in meta.get("tools", [])},
            # Each dependency is [tool_shed, name, owner, changeset_revision, ...].
            "depends_on": {(d[2], d[1], d[3]) for d in deps},
        })
    return revisions


def gxadmin_rows(sql):
    out = subprocess.run(["gxadmin", "tsvquery", "q", sql], capture_output=True, text=True, check=True).stdout
    return [line.split("\t") for line in out.splitlines() if line]


def job_counts(tool_ids):
    if not tool_ids:
        return {}
    ids = ",".join("'" + t.replace("'", "''") + "'" for t in sorted(tool_ids))
    return {t: int(n) for t, n in gxadmin_rows(f"select tool_id, count(*) from job where tool_id in ({ids}) group by tool_id")}


def decide(revisions, allow_jobs, only=None):
    by_repo = {}
    for r in revisions:
        by_repo.setdefault((r["owner"], r["name"]), []).append(r)
    depended = set().union(*(r["depends_on"] for r in revisions))

    rows = []
    for (owner, name), revs in sorted(by_repo.items()):
        if only and f"{owner}/{name}" not in only:
            continue
        try:
            installable = set(get(f"{TOOL_SHED}/api/repositories/get_ordered_installable_revisions", {"name": name, "owner": owner}))
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                raise
            installable = None
        for r in revs:
            if installable and r["revision"] in installable:
                continue
            row = {"owner": owner, "name": name, "revision": r["revision"], "decision": "keep",
                   "replacement": "", "jobs": 0, "tool_versions": len(r["tools"])}
            if installable is None:
                row["reason"] = "repository is gone from the Tool Shed"
                rows.append(row)
                continue
            replacements = [o["revision"] for o in revs
                            if o is not r and o["status"] == "Installed" and o["revision"] in installable
                            and r["tools"] <= o["tools"]]
            if r["status"] != "Installed":
                row["reason"] = f"status is {r['status']}"
            elif not r["tools"]:
                row["reason"] = "provides no tools"
            elif (owner, name, r["revision"]) in depended:
                row["reason"] = "another repository depends on it"
            elif not replacements:
                row["reason"] = "no installed revision provides the same tool versions"
            else:
                row["replacement"] = replacements[0]
                row["jobs"] = sum(job_counts(r["tools"]).values())
                if row["jobs"] and not allow_jobs:
                    row["reason"] = "its tool versions ran jobs"
                else:
                    row["decision"] = "uninstall"
                    row["reason"] = f"duplicate of {replacements[0]}"
            rows.append(row)
    return rows


def plan(args):
    rows = decide(installed_revisions(args.install_db), args.allow_jobs, set(args.only or []))
    with open(args.plan, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    n = sum(r["decision"] == "uninstall" for r in rows)
    print(f"{len(rows)} non-installable revisions, {n} to uninstall, plan in {args.plan}")


def apply(args):
    with open(args.plan) as f:
        planned = [r for r in csv.DictReader(f, delimiter="\t") if r["decision"] == "uninstall"]
    planned = planned[: args.limit] if args.limit else planned
    # Re-check against the current state, in case anything changed since the plan.
    current = {(r["owner"], r["name"], r["revision"]): r for r in decide(
        installed_revisions(args.install_db), args.allow_jobs, {f"{p['owner']}/{p['name']}" for p in planned})}
    api_key = os.environ.get(args.api_key_env) if args.yes else None
    if args.yes and not api_key:
        sys.exit(f"{args.api_key_env} is not set")
    for p in planned:
        key = (p["owner"], p["name"], p["revision"])
        now = current.get(key)
        if not now or now["decision"] != "uninstall":
            print(f"skip   {'/'.join(key)}: {now['reason'] if now else 'no longer installed'}")
            continue
        if not args.yes:
            print(f"would  {'/'.join(key)}: {now['reason']}")
            continue
        r = requests.delete(f"{args.galaxy}/api/tool_shed_repositories", timeout=600, headers={"x-api-key": api_key},
                            params={"tool_shed_url": TOOL_SHED, "name": p["name"], "owner": p["owner"],
                                    "changeset_revision": p["revision"], "remove_from_disk": True})
        if r.status_code != 200:
            sys.exit(f"failed {'/'.join(key)}: HTTP {r.status_code} {r.text[:200]}")
        print(f"done   {'/'.join(key)}: {now['reason']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--install-db", default=INSTALL_DB, help="Galaxy's install database (opened read-only)")
    parser.add_argument("--allow-jobs", action="store_true", help="also uninstall duplicates whose tool versions ran jobs")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("plan", help="TSV file to write")
    p.add_argument("--only", nargs="+", metavar="OWNER/NAME", help="limit to these repositories")
    a = sub.add_parser("apply")
    a.add_argument("plan", help="TSV file written by plan")
    a.add_argument("--galaxy", default="https://usegalaxy.be")
    a.add_argument("--api-key-env", default="GALAXY_API_KEY", help="environment variable holding an admin API key")
    a.add_argument("--limit", type=int, help="uninstall at most this many")
    a.add_argument("--yes", action="store_true", help="really uninstall")
    args = parser.parse_args()
    plan(args) if args.command == "plan" else apply(args)
