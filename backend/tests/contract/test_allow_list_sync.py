"""Contract: agent config YAML `allowed_tools` must equal allow_list.py (§5.4).

The allow-list is the runtime-enforced authority; the per-domain YAML files hand-copy it
for readability. This test fails on silent drift so the two artifacts stay identical.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tools.allow_list import AGENT_TOOL_ALLOW_LIST

_CONFIG_ROOT = Path(__file__).resolve().parents[1].parent / "agents"
_YAML_FILES = [
    _CONFIG_ROOT / "customer" / "config" / "agents.yaml",
    _CONFIG_ROOT / "merchant" / "config" / "agents.yaml",
]


def test_yaml_allowed_tools_match_allow_list():
    for path in _YAML_FILES:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for agent, spec in data.items():
            assert agent in AGENT_TOOL_ALLOW_LIST, f"{agent} missing from allow_list.py"
            yaml_tools = set(spec.get("allowed_tools", []))
            declared = set(AGENT_TOOL_ALLOW_LIST[agent])
            assert yaml_tools == declared, (
                f"{path.name}:{agent} allowed_tools drift: {yaml_tools} != {declared}"
            )
