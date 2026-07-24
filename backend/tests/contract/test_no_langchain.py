"""Contract: CrewAI must not pull LangChain into the dependency graph (plan guardrail).

We do not assert LangChain is absent from the whole environment (it may be installed
independently); we assert crewai does not *require* it, and that importing our CrewAI
integration modules does not import any `langchain*` package.
"""
from __future__ import annotations

import importlib
import importlib.metadata as md
import sys


def test_crewai_does_not_require_langchain():
    reqs = md.requires("crewai") or []
    offenders = [r for r in reqs if r.lower().startswith("langchain")]
    assert not offenders, f"crewai declares LangChain deps: {offenders}"


def test_importing_crew_modules_pulls_no_langchain():
    # Import the CrewAI-coupled modules, then confirm no langchain module got imported
    # as a side effect of *our* code path.
    for mod in ("agents.tool_adapter", "agents.customer.customer_crew",
                "agents.listeners.persisting_listener"):
        importlib.import_module(mod)
    langchain_mods = [m for m in sys.modules if m == "langchain" or m.startswith("langchain.")]
    assert not langchain_mods, f"langchain imported via crew modules: {langchain_mods}"
