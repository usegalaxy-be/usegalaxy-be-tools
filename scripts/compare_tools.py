import yaml
import argparse
import copy

def load_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def write_yaml(content, file_path, explicit_start=False):
    with open(file_path, 'w') as file:
        return yaml.dump(content, file, default_flow_style=False, explicit_start=explicit_start)

def merge_all_tools(*yaml_files):
    merged_tools = {}
    for yaml_file in yaml_files:
        tools_yaml = load_yaml(yaml_file)
        for tool in tools_yaml['tools']:
            merged_tools[tool['name']] = tool
    return {'tools': list(merged_tools.values())}


def deduplicate_tools(tools):
    """Merge duplicate tool entries with different tool_panel_section_label's keeping only the first label."""
    merged = {}
    
    for tool in tools:
        key = (tool['name'], tool['owner'])
        
        if key in merged:
            # Merge revisions
            merged[key]['revisions'] = sorted(set(merged[key]['revisions'] + tool['revisions']))
        else:
            # Store the first occurrence with its tool_panel_section_label
            merged[key] = tool.copy()

    return list(merged.values())

# Merges two tool.lock files. 
# Tools with the same name and owner are merged, combining their revisions without duplicates.
# The latest tool_panel_section_label is used if it differs between versions.
def merge_tools(data1, data2):
    """Merge a deduplicated data1 version with deduplicated data2."""
    merged_tools = {}
    for tool in data1['tools'] + data2['tools']:
        key = (tool['name'], tool['owner'])  # Unique identifier
        if key in merged_tools:
            merged_tools[key]['revisions'] = sorted(set(merged_tools[key]['revisions'] + tool['revisions']))
            merged_tools[key]['tool_panel_section_label'] = tool['tool_panel_section_label']
        else:
            merged_tools[key] = tool

    return {'tools': list(merged_tools.values())}

# Merges two tool.lock files (Only updating data1 entries). 
# Tools with the same name and owner are merged, combining their revisions without duplicates.
# The latest tool_panel_section_label is used if it differs between versions.
def merge_tools_left(data1, data2):
    """Merge a deduplicated data1 version with deduplicated data2."""
    deduplicated_tools1 = deduplicate_tools(data1["tools"])
    deduplicated_tools2 = deduplicate_tools(data2["tools"])

    tool_map = { (tool['name'], tool['owner']): tool for tool in deduplicated_tools1 }

    for tool in deduplicated_tools2:
        key = (tool['name'], tool['owner'])
        
        if key in tool_map:
            # Merge revisions, keep the tool_panel_section_label from data1
            tool_map[key]['revisions'] = sorted(set(tool_map[key]['revisions'] + tool['revisions']))

    return list(tool_map.values())

def collect_known_tools(yaml_docs):
    """Set of (name, owner) pairs declared across the given yaml.lock docs."""
    known = set()
    for doc in yaml_docs:
        for tool in deduplicate_tools(doc['tools']):
            known.add((tool['name'], tool['owner']))
    return known

def find_extra_tools(data2, all_found_tools):
    """Find tools in the currently installed tools that are not in any of the yaml.locks."""
    deduplicated_data2 = deduplicate_tools(data2['tools'])
    return [tool for tool in deduplicated_data2 if (tool['name'], tool['owner']) not in all_found_tools]

def declare_new_tools_in_base_yaml(extra_tools, base_yaml_path):
    """Add newly-discovered tools to the hand-maintained base yaml too, not just its lock."""
    base = load_yaml(base_yaml_path)
    known = {(tool['name'], tool['owner']) for tool in base['tools']}
    added = False
    for tool in extra_tools:
        key = (tool['name'], tool['owner'])
        if key in known:
            continue
        entry = {'name': tool['name'], 'owner': tool['owner']}
        if tool.get('tool_panel_section_label'):
            entry['tool_panel_section_label'] = tool['tool_panel_section_label']
        if tool.get('tool_shed_url'):
            entry['tool_shed_url'] = tool['tool_shed_url']
        base['tools'].append(entry)
        known.add(key)
        added = True
    if added:
        write_yaml(base, base_yaml_path, explicit_start=True)



def main():
    parser = argparse.ArgumentParser(description='Merge and compare Galaxy tool YAML files.')
    parser.add_argument('--current', required=True, help='Path to current_galaxy_tools.yaml')
    parser.add_argument('--inputs', nargs="+", required=True, help='Path to *.yaml.lock')
    args = parser.parse_args()

    current_tools = load_yaml(args.current)

    base_yaml = {'install_repository_dependencies': 'true',
        'install_resolver_dependencies': 'false',
        'install_tool_dependencies': 'false'}

    # Load every input up front so belgium-custom's extra-tool detection sees
    # tools_iuc/GTN's full tool sets, not just whatever loaded before it.
    input_yamls = {input: load_yaml(input) for input in args.inputs}
    all_found_tools = collect_known_tools(input_yamls.values())

    for input in args.inputs:
        yaml_lock = input_yamls[input]
        merged_yaml_lock = base_yaml.copy()
        if input == "belgium-custom.yaml.lock":
            # Add all extra tools to custom tools
            extra_tools = find_extra_tools(current_tools, all_found_tools)
            merged_yaml_lock["tools"] = merge_tools_left(yaml_lock, current_tools) + extra_tools
            declare_new_tools_in_base_yaml(extra_tools, "belgium-custom.yaml")
        else:
            merged_yaml_lock["tools"] = merge_tools_left(yaml_lock, current_tools)

        write_yaml(merged_yaml_lock, input)

    # extra_tools = base_yaml.copy()
    # extra_tools["tools"] = find_extra_tools(current_tools, input_yamls)
    # write_yaml(extra_tools, "extra.yaml.lock" )

if __name__ == "__main__":
    main()