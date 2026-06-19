"""Architecture tests that enforce layering rules across the core package.
"""
from __future__ import annotations

import importlib
import sys
from types import ModuleType
from unittest import TestCase


class AgentLayerBoundaryTests(TestCase):
    """The agent layer must remain read-only: no QB writes or QB client imports."""

    def _module_globals(self, module_name: str) -> dict:
        """Return a module's global namespace, importing it if needed."""
        if module_name not in sys.modules:
            importlib.import_module(module_name)
        return sys.modules[module_name].__dict__

    def _forbidden_references(self, module: ModuleType) -> list[str]:
        """Return any forbidden module references found in ``module`` globals."""
        forbidden = []
        for name, value in module.__dict__.items():
            if name.startswith("_"):
                continue
            module_path = getattr(value, "__module__", "")
            if module_path.startswith("core.services.qb_writes"):
                forbidden.append(f"{name} -> {module_path}")
            if module_path.startswith("core.quickbooks.client"):
                forbidden.append(f"{name} -> {module_path}")
        return forbidden

    def test_agent_reconcile_does_not_import_qb_writes_or_client(self) -> None:
        module = sys.modules.get("core.agent.reconcile")
        if module is None:
            module = importlib.import_module("core.agent.reconcile")
        forbidden = self._forbidden_references(module)
        self.assertEqual(
            forbidden,
            [],
            f"core.agent.reconcile contains forbidden QB write/client references: {forbidden}",
        )

    def test_agent_summary_does_not_import_qb_writes_or_client(self) -> None:
        module = sys.modules.get("core.agent.summary")
        if module is None:
            module = importlib.import_module("core.agent.summary")
        forbidden = self._forbidden_references(module)
        self.assertEqual(
            forbidden,
            [],
            f"core.agent.summary contains forbidden QB write/client references: {forbidden}",
        )
