"""Smoke tests for CI — no network or bot token required."""

import importlib
import sys
from pathlib import Path

import pytest


def test_import_config():
    config = importlib.import_module("config")
    assert config.FLIBUSTA_MIRRORS
    assert config.DB_PATH
    assert config.ADMIN_ID


def test_import_services():
    importlib.import_module("services.db")
    importlib.import_module("services.service")


def test_main_compiles():
    source = Path("main.py").read_text(encoding="utf-8")
    compile(source, "main.py", "exec")


@pytest.mark.skipif(sys.version_info < (3, 10), reason="requires Python 3.10+")
def test_import_main():
    importlib.import_module("main")
