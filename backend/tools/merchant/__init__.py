"""Merchant tools package (Dev B)."""
from tools.merchant import profile_tool, diagnosis_tool, competitor_tool
from tools.registry import registry

# Auto discover merchant tools into the global registry
profile_tool.register(registry)
diagnosis_tool.register(registry)
competitor_tool.register(registry)

__all__ = ["profile_tool", "diagnosis_tool", "competitor_tool"]
