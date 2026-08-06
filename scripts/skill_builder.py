#!/usr/bin/env python3
"""C-1: Skill Builder CLI - create a new skill from template."""
import sys
import os
from pathlib import Path

SKILLS_DIR = Path("/root/.hermes/skills")

TEMPLATE = """---
name: {name}
description: Use when {trigger}. {one_liner}.
---

# {title}

## Trigger

Load when {trigger}.

## What it does

{description}

## Steps

1. ...
2. ...
3. ...

## Example

```bash
# Example usage
```
"""


def build(name, trigger, description):
    if not name:
        print("Usage: skill_builder.py <name> [trigger] [description]")
        sys.exit(1)
    
    skill_dir = SKILLS_DIR / name
    if skill_dir.exists():
        print(f"Skill {name} already exists")
        sys.exit(1)
    
    skill_dir.mkdir(parents=True, exist_ok=True)
    title = name.replace("-", " ").title()
    content = TEMPLATE.format(
        name=name,
        trigger=trigger or "you need this skill",
        one_liner=description or "does the thing",
        title=title,
        description=description or "TODO",
    )
    (skill_dir / "SKILL.md").write_text(content)
    print(f"✓ Created skill: {skill_dir}/SKILL.md")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else None
    trigger = sys.argv[2] if len(sys.argv) > 2 else None
    description = sys.argv[3] if len(sys.argv) > 3 else None
    build(name, trigger, description)
