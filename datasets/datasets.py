#!/usr/bin/env python3
"""Datasets Registry (A-2) - Manage eval datasets."""
import os
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

DATASETS_DIR = Path("/root/.hermes/datasets")
REGISTRY = DATASETS_DIR / "registry.json"


def ensure_dirs():
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY.exists():
        REGISTRY.write_text(json.dumps({"datasets": {}}, indent=2))


def list_datasets():
    ensure_dirs()
    return json.loads(REGISTRY.read_text()).get("datasets", {})


def create_dataset(name, description=""):
    ensure_dirs()
    data = json.loads(REGISTRY.read_text())
    if name in data["datasets"]:
        return {"error": f"dataset {name} already exists"}
    data["datasets"][name] = {
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "size": 0,
        "file": str(DATASETS_DIR / f"{name}.jsonl"),
    }
    REGISTRY.write_text(json.dumps(data, indent=2))
    Path(data["datasets"][name]["file"]).touch()
    return data["datasets"][name]


def add_examples(name, examples):
    ensure_dirs()
    data = json.loads(REGISTRY.read_text())
    if name not in data["datasets"]:
        return {"error": f"dataset {name} does not exist"}
    info = data["datasets"][name]
    path = Path(info["file"])
    with open(path, "a") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    info["size"] = sum(1 for _ in open(path))
    info["updated_at"] = datetime.now(timezone.utc).isoformat()
    REGISTRY.write_text(json.dumps(data, indent=2))
    return info


def get_examples(name, limit=10):
    ensure_dirs()
    path = DATASETS_DIR / f"{name}.jsonl"
    if not path.exists():
        return []
    examples = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            try:
                examples.append(json.loads(line))
            except:
                pass
    return examples


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "list"
    if action == "list":
        print(json.dumps(list_datasets(), indent=2))
    elif action == "create":
        name = sys.argv[2]
        desc = sys.argv[3] if len(sys.argv) > 3 else ""
        print(json.dumps(create_dataset(name, desc), indent=2))
    elif action == "show":
        name = sys.argv[2]
        for ex in get_examples(name):
            print(json.dumps(ex))
    elif action == "seed":
        info = create_dataset("paragu-ai-onboarding", "Sample Q&A")
        add_examples("paragu-ai-onboarding", [
            {"prompt": "What is ParaguAI?", "expected": "site builder"},
            {"prompt": "How much?", "expected": "Gs 650K"},
            {"prompt": "How long?", "expected": "48 hours"},
        ])
        print(f"Seeded: {info['size']} examples")
    else:
        print(f"Unknown: {action}")
