"""Merchant tools package."""
from tools.merchant import diagnosis_tool, competitor_tool
from tools.registry import registry

# Auto discover merchant tools into the global registry
diagnosis_tool.register(registry)
competitor_tool.register(registry)

__all__ = [
    "profile_tool",
    "metrics_tool",
    "search_tool",
    "helper_tool",
    "diagnosis_tool",
    "competitor_tool",
    "complaints_tool",
    "menu_image_tool",
]
