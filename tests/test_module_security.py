"""Tests for custom module security validation."""

import tempfile
from mac_cleanup.module_security import validate_custom_module


def test_safe_module_validation():
    """Test that safe custom modules pass validation."""
    # Create a temporary safe module
    safe_content = '''"""Safe custom module."""
from mac_cleanup import *

clc = Collector()

def safe_function():
    """Safe cleanup function."""
    from mac_cleanup.utils import check_exists
    if check_exists("~/test"):
        with clc as unit:
            unit.message("Safe cleanup")
            unit.add(Path("~/test").with_prompt())
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(safe_content)
        f.flush()
        assert validate_custom_module(f.name)


def test_dangerous_module_validation():
    """Test that dangerous custom modules fail validation."""
    # Create a temporary dangerous module
    dangerous_content = '''"""Dangerous custom module."""
import os
import subprocess

def dangerous_function():
    """Dangerous function with system calls."""
    os.system("rm -rf /")
    subprocess.call(["sudo", "rm", "-rf", "/"])
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(dangerous_content)
        f.flush()
        assert not validate_custom_module(f.name)