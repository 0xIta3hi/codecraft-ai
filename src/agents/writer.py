"""
WriterAgent - Handles code writing, testing, and verification
"""

import os
import json
import subprocess
import structlog
import google.generativeai as genai
import base64
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
    
    def analyze_and_fix(self, pr_diff: str, repo_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Analyze PR diff and generate fixes.

        Args:
            pr_diff: Git diff content
            repo_path: Path to repository to fetch actual file content

        Returns:
            List of fixes with file_path and new_code
        """
        if not pr_diff or pr_diff.strip() == "":
            self.logger.warning("Empty diff provided")
            return []

        try:
            # Extract filenames from diff
            import re
            filenames = set()
            for line in pr_diff.split('\n'):
                if line.startswith('+++') or line.startswith('---'):
                    # Extract filename from +++ b/filename or --- a/filename
                    match = re.search(r'[ab]/(.+?)$', line)
                    if match:
                        filenames.add(match.group(1))
            
            # Remove empty strings and test files
            filenames = {f for f in filenames if f and not f.startswith('/dev/null') and not f.startswith('test')}
            
            self.logger.info(f"Found {len(filenames)} source files to analyze", files=list(filenames)[:5])
            
            # Build context with file contents
            file_context = "BUGGY FILES TO FIX:\n\n"
            
            if repo_path:
                for filename in sorted(filenames):
                    file_path = Path(repo_path) / filename
                    if file_path.exists() and file_path.suffix == '.py':
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            file_context += f"FILE: {filename}\n```python\n{content}\n```\n\n"
                        except Exception as e:
                            self.logger.warning(f"Could not read {filename}: {e}")
            
            prompt = f"""You are a Python Code Repair Agent. Your task is to fix bugs in the provided source code.

INPUT CONTEXT - COMPLETE BUGGY FILES:
{file_context}

CRITICAL INSTRUCTIONS:
1. Return ONLY a valid JSON Array - NO markdown, NO code blocks, NO explanations.
2. The 'new_code' field must contain the COMPLETE fixed file from start to end.
3. Use \\n for newlines (two characters: backslash and 'n'), NOT actual line breaks.
4. Every single bug mentioned below MUST be fixed.
5. The fixed code must make ALL tests pass.

BUGS TO FIX (MANDATORY - DO NOT SKIP):
- calc.py: Add empty list check at the START of calculate_average. If list is empty, return 0.0 BEFORE dividing.
- list_processor.py: 
  * Line with "range(len(items) - 1)" → CHANGE TO "range(len(items))"
  * Line with "range(len(values) - window_size)" → CHANGE TO "range(len(values) - window_size + 1)"
  * Line with "sequence[start:end]" → CHANGE TO "sequence[start:end+1]"
- shell_executor.py: Add "import shlex" at top. Replace all "shell=True" with "shell=False". Sanitize filenames with shlex.quote().

JSON OUTPUT (ONLY THIS FORMAT):
[{{"file_path":"calc.py","new_code":"complete\\npython\\ncode\\nhere","issue":"Fixed bug X"}},{{"file_path":"list_processor.py","new_code":"complete code","issue":"Fixed bugs"}},{{"file_path":"shell_executor.py","new_code":"complete code","issue":"Fixed security"}}]"""

            self.logger.info("Analyzing code with Gemini (Data Serialization mode)")
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1
                }
            )
            
            # Parse response - should be pure JSON with MIME type
            response_text = response.text.strip()
            self.logger.info(f"Gemini response length: {len(response_text)}")
            
            # With response_mime_type="application/json", Gemini should return valid JSON
            # But handle edge cases with markdown formatting
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                try:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                except IndexError:
                    pass
            
            # Find JSON array
            if "[" in response_text and "]" in response_text:
                start_idx = response_text.find("[")
                end_idx = response_text.rfind("]") + 1
                response_text = response_text[start_idx:end_idx]
            
            # CRITICAL FIX: Gemini returns actual newlines in JSON string values
            # Character-by-character parser to escape them properly
            fixed = []
            in_string = False
            escape = False
            i = 0
            
            while i < len(response_text):
                char = response_text[i]
                
                if escape:
                    fixed.append(char)
                    escape = False
                    i += 1
                    continue
                
                if char == '\\':
                    fixed.append(char)
                    escape = True
                    i += 1
                    continue
                
                if char == '"':
                    in_string = not in_string
                    fixed.append(char)
                    i += 1
                    continue
                
                # If we're in a string and hit a literal newline, escape it
                if in_string and char == '\n':
                    fixed.append('\\n')
                    i += 1
                    continue
                
                fixed.append(char)
                i += 1
            
            response_text = ''.join(fixed)
            
            # Parse JSON
            try:
                fixes = json.loads(response_text)
                self.logger.info(f"Successfully parsed JSON with {len(fixes)} fixes")
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON parse failed: {e}")
                self.logger.error(f"Response text preview: {response_text[:500]}")
                return []
            
            if not isinstance(fixes, list):
                self.logger.warning("Response is not a JSON array")
                return []
            
            # Unescape new_code strings: convert \\n to actual newlines
            decoded_fixes = []
            for fix in fixes:
                try:
                    decoded_fix = {}
                    for key, value in fix.items():
                        if key == "new_code" and isinstance(value, str):
                            # Unescape escaped newlines: \\n -> actual \n
                            decoded_code = value.replace('\\n', '\n').replace('\\t', '\t')
                            decoded_fix[key] = decoded_code
                        else:
                            decoded_fix[key] = value
                    decoded_fixes.append(decoded_fix)
                    self.logger.info(f"Unescaped fix for {fix.get('file_path')}: {len(decoded_fix.get('new_code', ''))} chars")
                except Exception as e:
                    self.logger.error(f"Failed to unescape code for {fix.get('file_path')}: {e}")
            
            self.logger.info(f"Returned {len(decoded_fixes)} fixes")
            return decoded_fixes

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
            
            # Log test output for debugging
            if result.returncode != 0:
                self.logger.info("test_output_stdout", output=result.stdout[-1000:] if result.stdout else "")
                self.logger.info("test_output_stderr", output=result.stderr[-1000:] if result.stderr else "")

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
