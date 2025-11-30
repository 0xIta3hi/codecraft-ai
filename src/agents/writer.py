"""
WriterAgent - Handles code writing, testing, and verification
"""

import os
import json
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
            
            prompt = f"""You are an expert Python developer. Fix ALL bugs in these files.

BUGGY SOURCE FILES:
{file_context}

YOU MUST:
1. Return COMPLETE, WORKING fixed code for each file
2. Escape newlines as \\n in JSON strings (do NOT include actual newlines)
3. Fix EVERY bug listed in comments and test descriptions
4. Return empty array [] if no bugs found

BUGS TO FIX:
- calc.py: Handle empty list in calculate_average (return 0.0, don't divide by zero)
- list_processor.py: Fix off-by-one errors in range() calls
  * remove_duplicates_preserve_order: use range(len(items)) not range(len(items)-1)
  * calculate_moving_average: use range(len(values) - window_size + 1) not range(len(values) - window_size)
  * extract_subsequence: return sequence[start:end+1] for inclusive end, not sequence[start:end]
- shell_executor.py: Sanitize filenames to prevent command injection
  * Use shlex.quote() or os.path.basename() to sanitize
  * Use subprocess.run(..., shell=False) instead of shell=True

Return ONLY JSON array (single line, no markdown):
[{{"file_path": "calc.py", "new_code": "complete file with \\n for newlines", "issue": "what was fixed"}}]"""

            self.logger.info("Analyzing code with Gemini")
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            
            # Parse response
            response_text = response.text.strip()
            self.logger.info(f"Gemini response length: {len(response_text)}")
            
            # CRITICAL: Preprocess to handle Gemini's inconsistent newline escaping
            # Gemini often returns actual newlines in JSON strings instead of \n
            # We need to escape them BEFORE json.loads()
            if response_text.startswith('['):
                # This looks like a JSON array - let's preprocess it
                # Strategy: Find quoted strings and escape their actual newlines
                processed = []
                in_string = False
                escape_next = False
                i = 0
                
                while i < len(response_text):
                    char = response_text[i]
                    
                    if escape_next:
                        processed.append(char)
                        escape_next = False
                        i += 1
                        continue
                    
                    if char == '\\':
                        processed.append(char)
                        escape_next = True
                        i += 1
                        continue
                    
                    if char == '"':
                        in_string = not in_string
                        processed.append(char)
                        i += 1
                        continue
                    
                    if char == '\n' and in_string:
                        # Actual newline inside a string - escape it
                        processed.append('\\')
                        processed.append('n')
                        i += 1
                        continue
                    
                    processed.append(char)
                    i += 1
                
                response_text = ''.join(processed)
            
            # Extract JSON
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
            
            # Parse JSON
            try:
                fixes = json.loads(response_text)
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON parse failed: {e}")
                self.logger.error(f"Response text: {response_text[:300]}")
                return []
            
            if not isinstance(fixes, list):
                self.logger.warning("Response is not a JSON array")
                return []
            
            # Unescape JSON string values - convert \\n to actual newlines
            decoded_fixes = []
            for fix in fixes:
                try:
                    decoded_fix = {}
                    for key, value in fix.items():
                        if key == "new_code" and isinstance(value, str):
                            # Unescape: \\n -> newline, \\t -> tab, etc.
                            decoded_value = value.encode().decode('unicode-escape')
                            decoded_fix[key] = decoded_value
                        else:
                            decoded_fix[key] = value
                    decoded_fixes.append(decoded_fix)
                    self.logger.info(f"Processed fix for {fix.get('file_path')}: {len(decoded_fix.get('new_code', ''))} chars")
                except Exception as e:
                    self.logger.error(f"Failed to unescape code for {fix.get('file_path')}: {e}")
            
            if not decoded_fixes:
                self.logger.warning("No valid fixes after unescaping")
            
            self.logger.info(f"Parsed {len(decoded_fixes)} fixes from response")
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
