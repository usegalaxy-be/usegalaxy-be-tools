import yaml
import argparse
import copy

def load_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def write_yaml(content, file_path):
    with open(file_path, 'w') as file:
        return yaml.dump(content, file, default_flow_style=False)

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

def find_extra_tools(data2, all_data1_versions):
    """Find tools in the currently installed tools that are not in any of the yaml.locks."""
    deduplicated_data2 = deduplicate_tools(data2['tools'])
    all_found_tools = set()

    # Collect all unique tool (name, owner) pairs from all data1 versions
    for data1 in all_data1_versions:
        deduplicated_data1 = deduplicate_tools(data1['tools'])
        for tool in deduplicated_data1:
            all_found_tools.add((tool['name'], tool['owner']))

    # Identify tools in data2 that are missing from all versions of data1
    return [tool for tool in deduplicated_data2 if (tool['name'], tool['owner']) not in all_found_tools]



def main():
    parser = argparse.ArgumentParser(description='Merge and compare Galaxy tool YAML files.')
    parser.add_argument('--current', required=True, help='Path to current_galaxy_tools.yaml')
    parser.add_argument('--inputs', nargs="+", required=True, help='Path to *.yaml.lock')
    args = parser.parse_args()

    current_tools = load_yaml(args.current)
    
    base_yaml = {'install_repository_dependencies': 'true',
        'install_resolver_dependencies': 'true',
        'install_tool_dependencies': 'false'}
    input_yamls = []    
    for input in args.inputs:
        yaml_lock = load_yaml(input)
        input_yamls.append(yaml_lock)
        merged_yaml_lock = base_yaml.copy()
        if input == "belgium-custom.yaml.lock":
            # Add all extra tools to custom tools
            merged_yaml_lock["tools"] = merge_tools_left(yaml_lock, current_tools) + find_extra_tools(current_tools, input_yamls)
        else:
            merged_yaml_lock["tools"] = merge_tools_left(yaml_lock, current_tools)
            
        write_yaml(merged_yaml_lock, input)

    # extra_tools = base_yaml.copy()
    # extra_tools["tools"] = find_extra_tools(current_tools, input_yamls)
    # write_yaml(extra_tools, "extra.yaml.lock" )

if __name__ == "__main__":
    main()