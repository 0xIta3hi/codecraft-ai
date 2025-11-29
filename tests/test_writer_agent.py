"""
Tests for WriterAgent.apply_fix_and_verify method
"""

import os
import tempfile
import pytest
from pathlib import Path
from src.agents.writer import WriterAgent


class TestWriterAgent:
    """Test suite for WriterAgent"""

    def setup_method(self):
        """Setup test fixtures"""
        self.agent = WriterAgent()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup after tests"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_apply_fix_and_verify_success(self):
        """Test successful fix application when tests pass"""
        # Create a simple test file
        test_file = Path(self.temp_dir) / "test_module.py"
        original_code = """
def add(a, b):
    return a + b
"""
        test_file.write_text(original_code)

        # New code (functionally equivalent)
        new_code = """
def add(a, b):
    '''Add two numbers'''
    return a + b
"""

        # Mock TEST_COMMAND to always succeed
        os.environ["TEST_COMMAND"] = "exit 0"

        success, error = self.agent.apply_fix_and_verify(str(test_file), new_code)

        assert success is True
        assert error is None
        assert test_file.read_text() == new_code

    def test_apply_fix_and_verify_failure_with_revert(self):
        """Test that file is reverted when tests fail"""
        test_file = Path(self.temp_dir) / "test_module.py"
        original_code = """
def add(a, b):
    return a + b
"""
        test_file.write_text(original_code)

        # New code that will "fail tests"
        new_code = """
def add(a, b):
    return a * b  # Wrong implementation
"""

        # Mock TEST_COMMAND to fail
        os.environ["TEST_COMMAND"] = "exit 1"

        success, error = self.agent.apply_fix_and_verify(str(test_file), new_code)

        assert success is False
        assert error is not None
        # File should be reverted to original
        assert test_file.read_text() == original_code

    def test_apply_fix_and_verify_nonexistent_file(self):
        """Test handling of nonexistent file"""
        nonexistent_file = Path(self.temp_dir) / "nonexistent.py"

        success, error = self.agent.apply_fix_and_verify(str(nonexistent_file), "new code")

        assert success is False
        assert error is not None
        assert "does not exist" in error.lower()

    def test_apply_fix_and_verify_timeout(self):
        """Test handling of test timeout"""
        test_file = Path(self.temp_dir) / "test_module.py"
        test_file.write_text("original code")

        # Mock TEST_COMMAND to sleep longer than timeout
        os.environ["TEST_COMMAND"] = "timeout 120"  # Command that will timeout

        success, error = self.agent.apply_fix_and_verify(str(test_file), "new code")

        assert success is False
        assert error is not None
        # File should be reverted
        assert test_file.read_text() == "original code"

    def test_apply_fix_and_verify_with_custom_test_command(self):
        """Test with custom TEST_COMMAND environment variable"""
        test_file = Path(self.temp_dir) / "test_module.py"
        original_code = "print('hello')"
        test_file.write_text(original_code)

        new_code = "print('world')"

        # Set custom test command that succeeds
        os.environ["TEST_COMMAND"] = "echo 'Running tests...' && exit 0"

        success, error = self.agent.apply_fix_and_verify(str(test_file), new_code)

        assert success is True
        assert error is None
        assert test_file.read_text() == new_code

    def test_apply_fix_and_verify_preserves_on_success(self):
        """Test that changes are preserved when tests pass"""
        test_file = Path(self.temp_dir) / "module.py"
        test_file.write_text("old code")

        new_code = "new code that is better"
        os.environ["TEST_COMMAND"] = "exit 0"

        success, error = self.agent.apply_fix_and_verify(str(test_file), new_code)

        assert success is True
        assert test_file.read_text() == new_code
        assert test_file.read_text() != "old code"
