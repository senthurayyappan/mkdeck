"""The public surface: what `mkdeck` exports, and that every module's `__all__` tells the truth."""

import ast
import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest

import mkdeck

SRC = Path(mkdeck.__file__).parent
MODULES = sorted(module.name for module in pkgutil.iter_modules(mkdeck.__path__) if module.name != "__main__")


def test_the_package_exports_the_minimum_coherent_surface() -> None:
    assert sorted(mkdeck.__all__) == [
        "DEFAULT_UNITS",
        "Deck",
        "DeckError",
        "DeckSource",
        "DeckWarning",
        "Embed",
        "Slide",
        "Table",
        "__version__",
        "load_source",
    ]
    for name in mkdeck.__all__:
        assert hasattr(mkdeck, name)


@pytest.mark.parametrize("name", MODULES)
def test_every_name_a_module_lists_exists(name: str) -> None:
    module = importlib.import_module(f"mkdeck.{name}")
    for exported in getattr(module, "__all__", []):
        assert hasattr(module, exported), f"mkdeck.{name}.__all__ lists {exported}, which the module lacks"


def _imports_from_mkdeck() -> list[tuple[str, str, str]]:
    """Every `from mkdeck.<module> import <name>` in the package, as (importer, module, name)."""
    found = []
    for path in sorted(SRC.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("mkdeck."):
                found.extend((path.name, node.module.removeprefix("mkdeck."), alias.name) for alias in node.names)
    return found


def test_a_module_imports_from_another_only_what_that_module_exports() -> None:
    for importer, module, name in _imports_from_mkdeck():
        exported = getattr(importlib.import_module(f"mkdeck.{module}"), "__all__", None)
        assert exported is None or name in exported, f"{importer} imports {name} from mkdeck.{module}, not in __all__"


def test_importing_the_package_loads_neither_the_server_nor_the_renderer() -> None:
    code = "import sys, mkdeck; print(sorted({'watchfiles', 'jinja2', 'mkdeck.server', 'mkdeck.render'} & set(sys.modules)))"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"
