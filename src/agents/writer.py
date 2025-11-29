"""
WriterAgent - Handles code writing, testing, and verification
"""

import os
import subprocess
import structlog
import google.generativeai as genai
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

logger = structlog.get_logger(__name__)


class WriterAgent:
    """Agent responsible for writing code changes and verifying them with tests"""

    def __init__(self):
        """Initialize WriterAgent"""
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Initialize Gemini API
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
    
    def analyze_and_fix(self, pr_diff: str) -> List[Dict[str, Any]]:
        """
        Analyze PR diff and generate fixes.

        Args:
            pr_diff: Git diff content

        Returns:
            List of fixes with file_path and new_code
        """
        if not pr_diff or pr_diff.strip() == "":
            self.logger.warning("Empty diff provided")
            return []

        try:
            prompt = f"""Analyze the following git diff and identify any code issues, bugs, or improvements.
For each issue found, provide the fix in a structured format.

GIT DIFF:
{pr_diff}

Please respond in the following JSON format ONLY:
[
    {{
        "issue": "Description of the issue",
        "file_path": "path/to/file.py",
        "new_code": "The corrected code snippet"
    }}
]

If no issues are found, return an empty array: []
Only return valid JSON, no other text."""

            self.logger.info("Analyzing diff with Gemini")
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            
            # Parse response
            response_text = response.text.strip()
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            import json
            fixes = json.loads(response_text)
            
            if not isinstance(fixes, list):
                self.logger.warning("Invalid response format from Gemini")
                return []
            
            self.logger.info("Fixes generated", count=len(fixes))
            return fixes

        except Exception as e:
            self.logger.error("Failed to analyze and fix", error=str(e))
            return []

    def apply_fix_and_verify(self, file_path: str, new_code: str) -> Tuple[bool, Optional[str]]:
        """
        Apply a code fix to a file and verify it with tests.

        Args:
            file_path: Path to the file to modify
            new_code: New code content to write to the file

        Returns:
            Tuple[bool, Optional[str]]: (success, error_logs)
                - (True, None) if tests pass
                - (False, stderr_logs) if tests fail (original file is restored)
        """
        file_path = Path(file_path)

        # Step 1: Read and backup current content
        try:
            if not file_path.exists():
                error_msg = f"File does not exist: {file_path}"
                self.logger.error("file_not_found", file_path=str(file_path))
                return False, error_msg

            with open(file_path, "r", encoding="utf-8") as f:
                backup_content = f.read()

            self.logger.info(
                "backup_created",
                file_path=str(file_path),
                backup_size=len(backup_content),
            )
        except Exception as e:
            error_msg = f"Failed to backup file: {str(e)}"
            self.logger.error("backup_failed", error=str(e), file_path=str(file_path))
            return False, error_msg

        # Step 2: Overwrite file with new code
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_code)

            self.logger.info("file_written", file_path=str(file_path), new_size=len(new_code))
        except Exception as e:
            error_msg = f"Failed to write new code: {str(e)}"
            self.logger.error("write_failed", error=str(e), file_path=str(file_path))
            return False, error_msg

        # Step 3: Run tests
        test_command = os.getenv("TEST_COMMAND", "pytest")
        self.logger.info("running_tests", test_command=test_command)

        try:
            result = subprocess.run(
                test_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(file_path.parent),
            )

            self.logger.info(
                "tests_completed",
                exit_code=result.returncode,
                stdout_length=len(result.stdout),
                stderr_length=len(result.stderr),
            )

            # Step 4: Check test results
            if result.returncode == 0:
                self.logger.info("tests_passed", file_path=str(file_path))
                return True, None
            else:
                # Tests failed: restore backup
                self.logger.warning(
                    "tests_failed",
                    file_path=str(file_path),
                    exit_code=result.returncode,
                )

                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(backup_content)

                    self.logger.info(
                        "file_reverted",
                        file_path=str(file_path),
                    )
                except Exception as e:
                    error_msg = f"Failed to revert file after test failure: {str(e)}"
                    self.logger.error("revert_failed", error=str(e))
                    return False, error_msg

                # Return failure with stderr logs
                return False, result.stderr

        except subprocess.TimeoutExpired:
            error_msg = "Tests timed out after 60 seconds"
            self.logger.error("tests_timeout")

            # Restore backup on timeout
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(backup_content)
                self.logger.info("file_reverted_after_timeout", file_path=str(file_path))
            except Exception as e:
                self.logger.error("revert_failed_after_timeout", error=str(e))

            return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error during test execution: {str(e)}"
            self.logger.error("test_execution_error", error=str(e))

            # Restore backup on unexpected error
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(backup_content)
                self.logger.info("file_reverted_after_error", file_path=str(file_path))
            except Exception as revert_error:
                self.logger.error("revert_failed_after_error", error=str(revert_error))

            return False, error_msg
