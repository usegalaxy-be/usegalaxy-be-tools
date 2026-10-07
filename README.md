 [![Install tools from the lock files (Ephemeris)](https://github.com/usegalaxy-be/usegalaxy-be-tools/actions/workflows/install_latest_tool_version.yml/badge.svg)](https://github.com/usegalaxy-be/usegalaxy-be-tools/actions/workflows/install_latest_tool_version.yml)
# usegalaxy.be tools

This repository contains the lists of tools installed on usegalaxy.be. The tools are split into 3 lists, each with a `.yaml` (requested tools) and a matching `.lock` file (pinned revisions, what actually gets installed):

- `tools_iuc.yaml(.lock)`: IUC and other Tool Shed tools installed on usegalaxy.be.
- `belgium-custom.yaml(.lock)`: tools installed only on usegalaxy.be.
- `GTN_tutorials_tools.yaml(.lock)`: tools used by [Galaxy Training Network](https://github.com/galaxyproject/training-material) tutorials, synced weekly from the `training-material` repo.

Manually requested tools are always added to `belgium-custom.yaml` unless they're iuc tools, in which case they can be added to `tools_iuc.yaml`.

These 3 `.lock` files are the only ones installed, by [`install_latest_tool_version.yml`](.github/workflows/install_latest_tool_version.yml). No manual step is needed to get a merged PR live.

The weekly updates only add new revisions of tools already in these lists, so every installed version stays available. New tools come from GTN, from installs through the admin UI (synced back by `sync_tools.yml`) or from a pull request.

Tool tests are run by the same role, but not by those weekly timers. Running the playbook with `test_tools: yes` starts `galaxy-tool-tests.service` once, which tests the tools installed since the date in `.last_test_since_date`. Separately, `galaxy-tool-tests-full.timer` re-tests everything once a year. So newly installed tools are only tested when someone applies the playbook, not automatically after each weekly install.

Other files in this repo are not deployed, they support the tooling above:

- `current_galaxy_tools.yaml`: a snapshot of the tools actually installed on usegalaxy.be, fetched weekly and diffed against the 3 lock files above (see [`sync_tools.yml`](.github/workflows/sync_tools.yml)) to catch drift, e.g. tools installed by hand through the admin panel. Not a source list, don't edit it by hand.
- `tool_conf.xml`: reference copy of the tool panel section labels/layout, used to keep `tool_panel_section_label` values in the yaml files consistent. The section labels actually deployed come from [`templates/galaxy/config/usegalaxy.be/tool_conf.xml.j2`](https://github.com/usegalaxy-be/infrastructure-playbook/blob/main/templates/galaxy/config/usegalaxy.be/tool_conf.xml.j2) in `infrastructure-playbook`, not from this file.
- `section_mapping.yml`: maps GTN tutorial topics to tool panel sections, used by [`scripts/gtn-tools-updater.py`](scripts/gtn-tools-updater.py).
- `.schema.yaml`: pykwalify schema used to lint the `.yaml` files.
- `requirements.txt`: pinned Python dependencies for the CI workflows below.

## Automated workflows

| Workflow | Runs | What it does |
|---|---|---|
| [`update-trusted.yml`](.github/workflows/update-trusted.yml) | Sat 01:00 UTC, starts the chain | Adds new Tool Shed revisions of the tools in `tools_iuc.yaml` and `belgium-custom.yaml`. |
| [`gtn-updater.yml`](.github/workflows/gtn-updater.yml) | after `update-trusted` | Adds tools used in current GTN tutorials to `GTN_tutorials_tools.yaml(.lock)`. |
| [`sync_tools.yml`](.github/workflows/sync_tools.yml) | after `gtn-updater` | Adds tools and revisions installed on usegalaxy.be outside the lock files, for example through the admin UI. |
| [`backfill-revisions.yml`](.github/workflows/backfill-revisions.yml) | after `sync_tools` | Adds every missing installable revision to the three lock files. |
| [`fix-outdated-tools.yml`](.github/workflows/fix-outdated-tools.yml) | after `backfill-revisions` | Replaces revisions that are no longer installable. |
| [`install_latest_tool_version.yml`](.github/workflows/install_latest_tool_version.yml) | after `fix-outdated-tools`, and on any other merge of a `.lock` file | Installs the revisions in the three lock files on usegalaxy.be, one list at a time, without resolver (conda) dependencies. |
| [`automerge.yml`](.github/workflows/automerge.yml) | Mon 06:00 UTC | Fallback: merges any PR labelled `automerge` whose own merge failed, then triggers the install. |

Each step opens a PR, merges it itself once `scripts/check_locks.py` passes, then starts the next step, so every step works on the previous step's merged result. The check fails on install flags that are not real booleans, and on any tool that disappears from a lock file. To run one step without the rest, start it by hand with `chain` unticked.

## Requesting Tools in usegalaxy.be

Open a pull request adding the tool to `tools_iuc.yaml` (IUC tools) or `belgium-custom.yaml` (anything else).

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

