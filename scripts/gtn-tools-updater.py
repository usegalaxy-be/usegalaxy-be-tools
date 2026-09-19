#!/usr/bin/env python

# Dependency: Ephemeris

import glob
import yaml
import os
import sys
import subprocess

# Path to output yaml file
output_file = sys.argv[2]

# Path to tools_iuc.yaml.lock 
tools_iuc = yaml.safe_load(open(sys.argv[3]))

# Path to mapping file directory
mapping_file = yaml.safe_load(open(sys.argv[4]))

# IUC and mapping lookup
def tool_exists (name, topic):
    # Use tool panel name from tools_iuc.yaml.lock when tools are already installed
    for tool in tools_iuc['tools']:
        if tool['name'] == name:
            if 'tool_panel_section_label' in tool:
                return tool['tool_panel_section_label']

    # if tool is in mapping file, use panel section label from mapping
    for section, tools in mapping_file['tool_mapping'].items():
        if name in tools:
            return section

    # If section is mapping file, use renamed section from mapping file
    if topic.title() in mapping_file['section_mapping']:
        return mapping_file['section_mapping'][topic.title()]
    else:
        return topic.title()

# Tool parsing
def toolyamltodict (yamlfile, baseyaml, topic):
    for i, tool in enumerate(yamlfile['tools']):
        yamlfile['tools'][i]['tool_panel_section_label'] = tool_exists(yamlfile['tools'][i]['name'], topic)
        baseyaml['tools'].append(tool)
    return baseyaml

def deduplicate_tools(tools):
    """Merge entries with the same name/owner, unioning the revisions each tutorial pinned."""
    merged = {}
    for tool in tools:
        key = (tool['name'], tool['owner'])
        if key in merged:
            merged[key]['revisions'] = sorted(set(merged[key]['revisions'] + tool.get('revisions', [])))
        else:
            merged[key] = tool.copy()
    return list(merged.values())

def sync_into_lock(tools, lock_path):
    """Add tutorial-pinned tools/revisions to the install lock, keeping whatever is already there."""
    with open(lock_path) as f:
        locked = yaml.safe_load(f)
    locked_by_key = {(t['name'], t['owner']): t for t in locked['tools']}

    for tool in tools:
        key = (tool['name'], tool['owner'])
        pinned = tool.get('revisions', [])
        if key not in locked_by_key:
            new_tool = {'name': tool['name'], 'owner': tool['owner'], 'revisions': sorted(set(pinned))}
            if tool.get('tool_panel_section_label'):
                new_tool['tool_panel_section_label'] = tool['tool_panel_section_label']
            if tool.get('tool_shed_url'):
                new_tool['tool_shed_url'] = tool['tool_shed_url']
            locked['tools'].append(new_tool)
            locked_by_key[key] = new_tool
        else:
            existing = locked_by_key[key].setdefault('revisions', [])
            locked_by_key[key]['revisions'] = sorted(set(existing) | set(pinned))

    with open(lock_path, 'w') as f:
        yaml.dump(locked, f, default_flow_style=False)


with open(output_file, "w") as f:

    baseyaml = { 'install_tool_dependencies': False, 'install_repository_dependencies': True, 'install_resolver_dependencies': False , 'tools':[]}

    # Determine topics
    topicslist = [f.name for f in os.scandir(f"{sys.argv[1]}/topics/") if f.is_dir()]
    topicslist.sort()

    # Generating the tool files and parse them for each workflow
    for topic in topicslist:
        print(f"\nParsing..... {topic}")
        topic_path = f"{sys.argv[1]}/topics/{topic}"
        for tutorial in [s.name for s in os.scandir(f"{topic_path}/tutorials") if s.is_dir()]:
            print("- " + tutorial)
            toolpath = f"{topic_path}/tutorials/{tutorial}/tools.yaml"
            workflowpath = f"{topic_path}/tutorials/{tutorial}/workflows"

            # if os.path.exists(workflowpath) and glob.glob(f"{workflowpath}/*.ga"):
            #     for nr, workflow in enumerate(glob.glob(f"{workflowpath}/*.ga")):
            #         os.system(f'workflow-to-tools -w "{workflow}" -o "{workflowpath}/temp_tool_{nr}.yaml"')
            #         worktools = yaml.safe_load(open(f"{workflowpath}/temp_tool_{nr}.yaml"))
            #         baseyaml = toolyamltodict(worktools, baseyaml, topic)
            #         os.remove(f"{workflowpath}/temp_tool_{nr}.yaml")

            if os.path.exists(workflowpath) and glob.glob(f"{workflowpath}/*.ga"):
                for nr, workflow in enumerate(glob.glob(f"{workflowpath}/*.ga")):
                    temp_tool_file = f"{workflowpath}/temp_tool_{nr}.yaml"

                    #using subprocess to call the external command as command failed previously on workflows with unexepcted characters in them
                    subprocess.run(
                        ["workflow-to-tools", "-w", workflow, "-o", temp_tool_file],
                        check=True  # Raises an exception if the command fails
                    )
                    #try-excepting to avoid ction failure
                    try:
                        with open(temp_tool_file, "r") as file:
                            worktools = yaml.safe_load(file)
                        baseyaml = toolyamltodict(worktools, baseyaml, topic)
                    except FileNotFoundError:
                        print(f"Warning: Temporary tool file {temp_tool_file} not found.")
                    except yaml.YAMLError as e:
                        print(f"Error parsing YAML file {temp_tool_file}: {e}")
                    finally:
                        if os.path.exists(temp_tool_file):
                            os.remove(temp_tool_file)

    # Consolidate duplicate tool entries from different tutorials before writing.
    baseyaml['tools'] = deduplicate_tools(baseyaml['tools'])

    # Dump newly generated dictionary to yaml
    yaml.dump(baseyaml, f, default_flow_style=False)

# Carry newly-found tools/revisions into the install lock too.
sync_into_lock(baseyaml['tools'], output_file + '.lock')
