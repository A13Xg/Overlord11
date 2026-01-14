import os
import json
import re

def extract_python_tool_info(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract function name
    func_name_match = re.search(r"def (\w+)", content)
    func_name = func_name_match.group(1) if func_name_match else None

    # Extract docstring (description)
    docstring_match = re.search(r'"""(.*?)(""")', content, re.DOTALL)
    docstring = docstring_match.group(1).strip() if docstring_match else ""
    # Clean up common docstring leading/trailing newlines/spaces
    docstring = ' '.join(docstring.split())

    # Extract parameters
    params_match = re.search(r"def \w+\((.*?)\)", content, re.DOTALL)
    params_str = params_match.group(1) if params_match else ""
    
    python_params = {}
    if params_str:
        # Adjusted regex to capture more complex type hints
        # It looks for word (param name), then ':', then anything not ',' or '=' (the type hint)
        raw_params = re.findall(r'(\w+)\s*:\s*([^,=]+?)(?:\s*=\s*[^,]+)?', params_str)
        for name, p_type in raw_params:
            python_params[name] = p_type.strip() # Store the stripped type


    return func_name, docstring, python_params

def compare_tools(json_files_list, python_files_list, tools_defs_dir, tools_python_dir):
    discrepancies = []
    json_tools = {}
    python_tools = {}

    # Process JSON files
    for json_file in json_files_list:
        try:
            with open(os.path.join(tools_defs_dir, json_file), 'r', encoding='utf-8') as f:
                data = json.load(f)
                tool_name = data.get('name')
                json_tools[tool_name] = data
        except Exception as e:
            discrepancies.append(f"Error reading JSON file {json_file}: {e}")

    # Process Python files
    for py_file in python_files_list:
        if py_file == "__pycache__": # Skip the __pycache__ directory
            continue
        try:
            func_name, docstring, params = extract_python_tool_info(os.path.join(tools_python_dir, py_file))
            if func_name:
                python_tools[func_name] = {
                    'docstring': docstring,
                    'params': params,
                    'file': py_file
                }
            else:
                discrepancies.append(f"Could not extract function name from Python file: {py_file}")
        except Exception as e:
            discrepancies.append(f"Error reading Python file {py_file}: {e}")

    # Validate pairs and schema consistency
    all_tool_names = set(json_tools.keys()).union(set(python_tools.keys()))

    for tool_name in sorted(list(all_tool_names)):
        json_info = json_tools.get(tool_name)
        python_info = python_tools.get(tool_name)
        
        # Check for missing pairs
        if not json_info:
            discrepancies.append(f"DISCREPANCY: JSON definition missing for Python tool '{tool_name}' ({python_info['file']}).")
            continue # Can't compare further without JSON
        if not python_info:
            # Special case: delegate_to_agent has no .py file
            if tool_name == "delegate_to_agent":
                continue 
            # For glob and replace, the JSON names are 'glob' and 'replace'
            # but python files are 'glob_tool.py' and 'replace_tool.py' if the renaming was not done
            # Check for alternative python file names if the direct match failed
            py_file_expected_name = tool_name + ".py"
            found_alt_py = False
            for py_name, py_data in python_tools.items():
                if py_name == tool_name: # already handled
                    continue
                if py_data['file'] == py_file_expected_name:
                    python_info = py_data
                    discrepancies.append(f"DISCREPANCY: Python tool '{tool_name}' found as '{py_data['file']}' but function name is '{py_name}'. Expected function name '{tool_name}'.")
                    found_alt_py = True
                    break
            
            if not found_alt_py and tool_name != "delegate_to_agent":
                discrepancies.append(f"DISCREPANCY: Python implementation missing for JSON tool '{tool_name}' (expected {tool_name}.py).")
            continue # Can't compare further without Python info

        # Compare name (already implicit by dictionary keys matching)

        # Compare description/docstring
        json_desc = json_info.get('description', '').strip()
        # Clean up description for comparison (remove extra newlines/spaces)
        json_desc = ' '.join(json_desc.split())
        python_docstring = python_info.get('docstring', '').strip()
        if not python_docstring.startswith(json_desc.split('.')[0]): # Compare first sentence or general start
            discrepancies.append(f"DISCREPANCY for '{tool_name}': Python docstring '{python_docstring[:50]}...' does not closely match JSON description '{json_desc[:50]}...'.")

        # Compare parameters
        json_params_props = json_info.get('parameters', {}).get('properties', {})
        json_required_params = set(json_info.get('parameters', {}).get('required', []))
        python_params = python_info.get('params', {})
        
        # Check if all required JSON params are in Python
        for param_name in json_required_params:
            if param_name not in python_params:
                discrepancies.append(f"DISCREPANCY for '{tool_name}': Required JSON parameter '{param_name}' missing in Python function signature.")

        # Check if all JSON params are in Python (and their types - basic check)
        for param_name, json_param_info in json_params_props.items():
            if param_name not in python_params:
                discrepancies.append(f"DISCREPANCY for '{tool_name}': JSON parameter '{param_name}' missing in Python function signature.")
            # Basic type check: JSON types like "STRING", "NUMBER", "BOOLEAN", "ARRAY", "OBJECT"
            # Python types like "str", "float", "int", "bool", "list", "dict"
            # This is a very rough comparison
            json_type = json_param_info.get('type').lower()
            python_type = python_params.get(param_name, '').lower()

            python_raw_type = python_params.get(param_name, '').strip()
            
            # Extract base type from complex type hints (e.g., Optional[str] -> str, List[str] -> list)
            match_optional = re.match(r'Optional\[(\w+)\]', python_raw_type)
            match_list = re.match(r'List\[(\w+)\]', python_raw_type)
            match_dict = re.match(r'Dict\[(\w+),\s*(\w+)\]', python_raw_type)
            
            if match_optional:
                python_base_type_str = match_optional.group(1).lower()
            elif match_list:
                python_base_type_str = 'list' # JSON array
            elif match_dict:
                python_base_type_str = 'object' # JSON object
            else:
                python_base_type_str = python_raw_type.lower()

            # Map Python types to a common base for comparison
            python_type_map = {
                'str': 'string',
                'float': 'number',
                'int': 'number',
                'bool': 'boolean',
                'list': 'array',
                'dict': 'object',
                'any': 'any'
            }
            mapped_python_type = python_type_map.get(python_base_type_str, python_base_type_str)

            if json_type != mapped_python_type:
                discrepancies.append(f"DISCREPANCY for '{tool_name}' parameter '{param_name}': JSON type '{json_type}' does not match Python type '{python_raw_type}' (mapped to '{mapped_python_type}').")


        # Check for Python-only parameters that are not in JSON
        for param_name in python_params:
            if param_name not in json_params_props:
                # Allow for self (implicit Python parameter)
                if param_name != 'self':
                    discrepancies.append(f"DISCREPANCY for '{tool_name}': Python function has parameter '{param_name}' not defined in JSON.")

    return discrepancies

if __name__ == '__main__':
    tools_defs_dir = 'tools/defs'
    tools_python_dir = 'tools/python'

    json_files = [f for f in os.listdir(tools_defs_dir) if f.endswith('.json')]
    python_files = [f for f in os.listdir(tools_python_dir) if f.endswith('.py') or os.path.isdir(os.path.join(tools_python_dir, f))] # Include directories to filter out __pycache__

    discrepancies_list = compare_tools(json_files, python_files, tools_defs_dir, tools_python_dir)

    if discrepancies_list:
        print("Discrepancies found:")
        for disc in discrepancies_list:
            print(f"- {disc}")
    else:
        print("No discrepancies found between JSON definitions and Python implementations (excluding 'delegate_to_agent').")

    # Generate requirements.txt
    dependencies = set()
    for py_file in python_files:
        if py_file == "__pycache__":
            continue
        try:
            with open(os.path.join(tools_python_dir, py_file), 'r', encoding='utf-8') as f:
                content = f.read()
                # Find import statements
                # Basic imports like 'import requests'
                imports = re.findall(r"^\s*import (\w+)", content, re.MULTILINE)
                for imp in imports:
                    # Comprehensive list of built-in/standard library modules often imported
                    if imp not in ['os', 'sys', 'json', 're', 'datetime', 'math', 'subprocess', 'typing', 'glob', 'collections', 'io', 'shutil', 'tempfile', 'logging', 'argparse', 'csv', 'yaml', 'xml', 'hashlib', 'base64', 'urllib', 'pathlib']:
                        dependencies.add(imp)
                
                # From imports like 'from requests import get'
                from_imports = re.findall(r"^\s*from (\w+)", content, re.MULTILINE)
                for imp in from_imports:
                    # Comprehensive list of built-in/standard library modules often imported
                    if imp not in ['os', 'sys', 'json', 're', 'datetime', 'math', 'subprocess', 'typing', 'glob', 'collections', 'io', 'shutil', 'tempfile', 'logging', 'argparse', 'csv', 'yaml', 'xml', 'hashlib', 'base64', 'urllib', 'pathlib']:
                        dependencies.add(imp)
        except Exception as e:
            print(f"Error processing Python file {py_file} for dependencies: {e}")
            
    # Manually add requests since it was explicitly missing and installed
    dependencies.add('requests')


    if dependencies:
        with open('requirements.txt', 'w', encoding='utf-8') as f:
            for dep in sorted(list(dependencies)):
                f.write(f"{dep}\n")
        print("\nGenerated requirements.txt with the following dependencies:")
        for dep in sorted(list(dependencies)):
            print(f"- {dep}")
    else:
        print("\nNo external dependencies found for requirements.txt.")
