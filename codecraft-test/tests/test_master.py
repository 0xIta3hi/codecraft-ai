import pytest
import os
import pytest

import os

import pytest


def test_master_md_exists():
    """Tests that the master.md file exists."""
    assert os.path.exists('master.md')


def test_master_md_not_empty():
    """Tests that the master.md file is not empty."""
    assert os.path.getsize('master.md') > 0, "master.md should not be empty"


def test_master_md_is_readable():
    """Tests that master.md is readable."""
    try:
        with open('master.md', 'r') as f:
            f.read()
    except Exception as e:
        pytest.fail(f"Failed to read master.md: {e}")