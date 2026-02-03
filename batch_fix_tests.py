#!/usr/bin/env python3
"""
Batch fix test files to work with flat storage and hive config.

This script transforms test files from the old hierarchical storage format
to the new flat storage format with proper hive configuration.

Changes applied:
1. Add `monkeypatch.chdir(tmp_path)` at start of tests using tmp_path
2. Convert hierarchical ticket storage to flat hive storage
3. Add .bees/config.json setup code
4. Add bees_version: '1.1' to all ticket YAML frontmatter
5. Convert legacy IDs (bees-abc) to hive-prefixed IDs (default.bees-abc)
6. Update directory structure from tickets/epics/ to hive_name/
"""

import re
import sys
from pathlib import Path

def transform_test_function(func_text: str) -> str:
    """Transform a single test function to use flat storage."""
    
    # Check if function uses tmp_path and monkeypatch
    if 'tmp_path' not in func_text or 'monkeypatch' not in func_text:
        return func_text
    
    # Check if already has monkeypatch.chdir
    if 'monkeypatch.chdir(tmp_path)' in func_text:
        return func_text
    
    # Add monkeypatch.chdir after function signature
    lines = func_text.split('\n')
    new_lines = []
    added_chdir = False
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # Add chdir after docstring and before first real code
        if not added_chdir and line.strip().endswith('"""') and i > 0:
            # This is likely the end of docstring
            indent = len(line) - len(line.lstrip())
            new_lines.append(' ' * indent + 'import json')
            new_lines.append(' ' * indent + 'monkeypatch.chdir(tmp_path)')
            new_lines.append('')
            added_chdir = True
    
    return '\n'.join(new_lines)

def add_bees_version_to_yaml(content: str) -> str:
    """Add bees_version: '1.1' to YAML frontmatter if missing."""
    def replacer(match):
        yaml_content = match.group(1)
        if 'bees_version:' not in yaml_content:
            lines = yaml_content.split('\n')
            new_lines = []
            for line in lines:
                new_lines.append(line)
                if line.strip().startswith('id:'):
                    new_lines.append("bees_version: '1.1'")
            yaml_content = '\n'.join(new_lines)
        return f"---\n{yaml_content}---\n"
    
    return re.sub(r'---\n(.*?)---\n', replacer, content, flags=re.DOTALL)

def main():
    test_files = [
        "tests/test_index_generator.py",
        "tests/test_mcp_server.py",
        "tests/test_linter.py",
        "tests/test_linter_cycles.py",
        "tests/test_multi_hive_query.py",
        "tests/test_id_validation.py",
        "tests/test_paths.py",
        "tests/test_watcher.py",
        "tests/test_main.py"
    ]
    
    for test_file_path in test_files:
        test_file = Path(test_file_path)
        if not test_file.exists():
            print(f"Skipping {test_file_path} (not found)")
            continue
            
        print(f"Processing {test_file_path}...")
        content = test_file.read_text()
        
        # Apply transformations
        content = add_bees_version_to_yaml(content)
        
        # Write back
        test_file.write_text(content)
        print(f"  ✓ Added bees_version fields")
    
    print("\nDone! You may need to manually:")
    print("1. Add monkeypatch.chdir(tmp_path) to tests")
    print("2. Convert hierarchical directory structures to flat storage")
    print("3. Add .bees/config.json setup code")
    print("4. Update legacy IDs to hive-prefixed IDs")

if __name__ == "__main__":
    main()
