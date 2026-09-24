 [![Update Galaxy BE tools with their latest version (Ephemeris)](https://github.com/usegalaxy-be/usegalaxy-be-tools/actions/workflows/install_latest_tool_version.yml/badge.svg)](https://github.com/usegalaxy-be/usegalaxy-be-tools/actions/workflows/install_latest_tool_version.yml)
# usegalaxy.be tools

This repository contains the lists of tools installed on usegalaxy.be. The tools are split into 3 lists, each with a `.yaml` (requested tools) and a matching `.lock` file (pinned revisions, what actually gets installed):

- `tools_iuc.yaml(.lock)`: the IUC tool list, merged in weekly from [usegalaxy-eu-tools](https://github.com/usegalaxy-eu/usegalaxy-eu-tools).
- `belgium-custom.yaml(.lock)`: tools installed only on usegalaxy.be.
- `GTN_tutorials_tools.yaml(.lock)`: tools used by [Galaxy Training Network](https://github.com/galaxyproject/training-material) tutorials, synced weekly from the `training-material` repo.

Manually requested tools are always added to `belgium-custom.yaml` unless they're iuc tools, in which case they can be added to `tools_iuc.yaml`.

These 3 `.lock` files are the only ones actually deployed: the [`pdg.galaxy-tools`](https://github.com/usegalaxy-be/infrastructure-playbook/tree/main/roles/pdg.galaxy-tools) role in `infrastructure-playbook` installs from them ([`galaxy_tools_tool_list_files`](https://github.com/usegalaxy-be/infrastructure-playbook/blob/main/roles/pdg.galaxy-tools/defaults/main.yml)), one `.lock` file per day, each on its own weekly systemd timer ([`galaxy_tools_install_schedule`](https://github.com/usegalaxy-be/infrastructure-playbook/blob/main/roles/pdg.galaxy-tools/defaults/main.yml)). No manual step is needed to get a merged PR live: the next scheduled install picks it up. The role is applied by [`daily-galaxy-tools.yml`](https://github.com/usegalaxy-be/infrastructure-playbook/blob/main/playbooks/daily/daily-galaxy-tools.yml).

Tool tests are run by the same role, but not by those weekly timers. Running the playbook with `test_tools: yes` starts `galaxy-tool-tests.service` once, which tests the tools installed since the date in `.last_test_since_date`. Separately, `galaxy-tool-tests-full.timer` re-tests everything once a year. So newly installed tools are only tested when someone applies the playbook, not automatically after each weekly install.

Other files in this repo are not deployed, they support the tooling above:

- `current_galaxy_tools.yaml`: a snapshot of the tools actually installed on usegalaxy.be, fetched weekly and diffed against the 3 lock files above (see [`sync_tools.yml`](.github/workflows/sync_tools.yml)) to catch drift, e.g. tools installed by hand through the admin panel. Not a source list, don't edit it by hand.
- `tool_conf.xml`: reference copy of the tool panel section labels/layout, used to keep `tool_panel_section_label` values in the yaml files consistent. The section labels actually deployed come from [`templates/galaxy/config/usegalaxy.be/tool_conf.xml.j2`](https://github.com/usegalaxy-be/infrastructure-playbook/blob/main/templates/galaxy/config/usegalaxy.be/tool_conf.xml.j2) in `infrastructure-playbook`, not from this file.
- `section_mapping.yml`: maps GTN tutorial topics to tool panel sections, used by [`scripts/gtn-tools-updater.py`](scripts/gtn-tools-updater.py).
- `.schema.yaml`: pykwalify schema used to lint the `.yaml` files.
- `requirements.txt`: pinned Python dependencies for the CI workflows below.

## Automated workflows

| Workflow | Schedule (UTC) | What it does |
|---|---|---|
| [`update-trusted.yml`](.github/workflows/update-trusted.yml) | Sat 02:00 | Merges `tools_iuc.yaml` from usegalaxy-eu-tools, updates both lock files, opens a PR. |
| [`gtn-updater.yml`](.github/workflows/gtn-updater.yml) | Sat 02:30 | Re-syncs `GTN_tutorials_tools.yaml(.lock)` against the current `training-material` repo, opens a PR. |
| [`sync_tools.yml`](.github/workflows/sync_tools.yml) | Sat 03:00 | Refreshes `current_galaxy_tools.yaml` and diffs it against the 3 lock files, opens a PR to flag drift. |
| [`backfill-revisions.yml`](.github/workflows/backfill-revisions.yml) | Sat 01:00 | Adds any installable tool revisions missing from the lock files. Manual review, no `automerge` label. |
| [`fix-outdated-tools.yml`](.github/workflows/fix-outdated-tools.yml) | Sat 04:00 | Removes revisions from the lock files that are no longer installable. Manual review, no `automerge` label. |
| [`install_latest_tool_version.yml`](.github/workflows/install_latest_tool_version.yml) | Mon 01:00 | Runs `shed-tools update` directly against usegalaxy.be to update tools already installed to their latest revision. |
| [`automerge.yml`](.github/workflows/automerge.yml) | Mon 06:00 | Merges any open PR labelled `automerge`. |

The Saturday jobs are staggered so they don't open colliding PRs against the same files.

## Requesting Tools in usegalaxy.be

There are 2 ways to get a tool included in usegalaxy.be:

- Follow the procedure to add it to the tools_iuc list in https://github.com/usegalaxy-eu/usegalaxy-eu-tools
- Open a pull request adding it to `belgium-custom.yaml` in this repository.

For the second option:

### Updating an Existing Tool

- Edit the `.yaml.lock` file to add the latest/specific changeset revision for the tool. You can use [`scripts/update-tool.py`](scripts/update-tool.py) if you just want to add the latest revision: `python scripts/update-tool.py --owner <repo-owner> --name <repo-name> <file.yaml.lock>`
- Open a pull request

### Requesting a New Tool

- If you just want the latest version:
	- Edit the `.yaml` file to add name/owner/section
- If you want a specific version:
	- Edit the `.yaml` file to add name/owner/section
	- Run `make fix`
	- Edit the `.yaml.lock` to correct the version number.
- Open a pull request

Always stick to the section names in `tool_conf.xml`.

## For UseGalaxy.\* Instance Administrators

On usegalaxy.be, tools are installed by the [`pdg.galaxy-tools`](https://github.com/usegalaxy-be/infrastructure-playbook/tree/main/roles/pdg.galaxy-tools) role in `infrastructure-playbook`, not by hand from this repo. If you're running your own instance from these lists instead, set the environment variables `GALAXY_SERVER_URL` and `GALAXY_API_KEY` and run `make install`. This installs all tools from the `.lock` files. Make sure the tool panel sections are pre-defined in your `tool_conf.xml`, or this can create a mess in your tool panel. Run `grep -o -h 'tool_panel_section_label:.*' *.yaml.lock | sort -u` for a list of categories.

`install_resolver_dependencies` is set per tool in the yaml files. On usegalaxy.be it's `false` everywhere, since jobs run in containers and the conda envs built at install time are never used. Set it `true` if you install tools without container resolution and want their conda dependencies available right away, rather than resolved later at runtime.

