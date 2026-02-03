#!/usr/bin/env python3
"""
Script to help fix test files by adding:
1. monkeypatch.chdir(tmp_path)
2. bees_version: '1.1' to all YAML frontmatter
3. Proper hive-prefixed IDs
4. .bees/config.json setup
5. Flat storage structure
"""

import re
import sys
from pathlib import Path

def add_bees_version_to_yaml(content: str) -> str:
    """Add bees_version: '1.1' to YAML frontmatter if missing."""
    # Pattern to match YAML frontmatter
    pattern = r'(---\n)(.*?)(---\n)'
    
    def replacer(match):
        yaml_content = match.group(2)
        if 'bees_version:' not in yaml_content:
            # Add bees_version after first line or at start
            lines = yaml_content.split('\n')
            if lines and lines[0].strip():
                # Insert after id line if it exists
                for i, line in enumerate(lines):
                    if line.startswith('id:'):
                        lines.insert(i+1, "bees_version: '1.1'")
                        break
                else:
                    # No id line, insert at beginning
                    lines.insert(0, "bees_version: '1.1'")
            yaml_content = '\n'.join(lines)
        return f"{match.group(1)}{yaml_content}{match.group(3)}"
    
    return re.sub(pattern, replacer, content, flags=re.DOTALL)

def main():
    test_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/test_index_generator.py")
    content = test_file.read_text()
    
    # Add bees_version to all YAML frontmatter
    content = add_bees_version_to_yaml(content)
    
    test_file.write_text(content)
    print(f"Updated {test_file}")

if __name__ == "__main__":
    main()
