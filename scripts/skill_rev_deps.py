#!/usr/bin/env python3
"""C-22: Skill Reverse Dependencies - which skills use this one."""
import sys
from pathlib import Path
import re

SKILLS_DIR = Path("/root/.hermes/skills")
SCRIPTS_DIR = Path("/root/.hermes/scripts")


def find_refs(target):
    """Find all skills/scripts that reference `target`."""
    refs = []
    
    # Search skills
    for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
        content = skill_md.read_text()
        if target in content:
            refs.append(f"skill: {skill_md.parent.name}")
    
    # Search scripts
    for script in SCRIPTS_DIR.glob("*.py"):
        try:
            content = script.read_text()
        except:
            continue
        if target in content:
            refs.append(f"script: {script.name}")
    
    return refs


def main():
    if len(sys.argv) < 2:
        print("Usage: skill_rev_deps.py <name>")
        sys.exit(1)
    target = sys.argv[1]
    refs = find_refs(target)
    print(f"References to {target}: {len(refs)}")
    for r in refs:
        print(f"  {r}")


if __name__ == "__main__":
    main()
