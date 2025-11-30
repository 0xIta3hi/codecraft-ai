"""
TestAgent - Autonomously generates pytest test cases for uncovered code
"""

import os
import json
import structlog
import google.generativeai as genai
from typing import Dict, Any, List
from pathlib import Path

logger = structlog.get_logger(__name__)


class TestAgent:
    """Agent responsible for autonomous test case generation"""

    def __init__(self):
        """Initialize TestAgent"""
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Initialize Gemini API
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)

    def generate_test_cases(self, pr_diff: str, changed_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate pytest test cases for uncovered code in the PR.

        Args:
            pr_diff: Git diff content
            changed_files: List of changed files with metadata

        Returns:
            List of generated test cases with file path and code
        """
        if not pr_diff or pr_diff.strip() == "":
            self.logger.warning("Empty diff provided for test generation")
            return []

        try:
            files_info = json.dumps(changed_files, indent=2)
            
            prompt = f"""Analyze this PR diff and generate comprehensive pytest test cases for the changed code.
Focus on:
1. Unit tests for new functions/methods
2. Edge cases and boundary conditions
3. Error handling and exceptions
4. Integration points

CHANGED FILES:
{files_info}

GIT DIFF (first 5000 chars):
{pr_diff[:5000]}

Respond in JSON format ONLY:
[
    {{
        "file": "path/to/test_file.py",
        "target_file": "path/to/original_file.py",
        "test_code": "Complete pytest test case code",
        "description": "What this test covers",
        "imports": ["required", "imports"]
    }}
]

Generate 2-5 test cases maximum. Return ONLY valid JSON array."""

            self.logger.info("Generating test cases with Gemini")
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            
            # Parse response
            response_text = response.text.strip()
            
            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            test_cases = json.loads(response_text)
            
            if not isinstance(test_cases, list):
                self.logger.warning("Invalid response format from Gemini")
                return []
            
            self.logger.info("Test cases generated", count=len(test_cases))
            return test_cases

        except Exception as e:
            self.logger.error("Test case generation failed", error=str(e))
            return []

    def write_test_file(self, test_file_path: str, test_code: str, imports: List[str]) -> bool:
        """
        Write generated test code to a test file.

        Args:
            test_file_path: Path where test file should be created
            test_code: The test case code
            imports: List of import statements needed

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            Path(test_file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Build imports section
            import_section = "\n".join([f"import {imp}" if not imp.startswith("from") else imp for imp in imports])
            if not import_section.startswith("import pytest"):
                import_section = "import pytest\n" + import_section
            
            # Combine imports and test code
            full_code = f"{import_section}\n\n{test_code}"
            
            # Write to file
            with open(test_file_path, "w", encoding="utf-8") as f:
                f.write(full_code)
            
            self.logger.info("Test file written", path=test_file_path)
            return True

        except Exception as e:
            self.logger.error("Failed to write test file", error=str(e), path=test_file_path)
            return False

    def generate_test_report(self, test_cases: List[Dict[str, Any]]) -> str:
        """
        Generate a report of generated test cases.

        Args:
            test_cases: List of generated test cases

        Returns:
            Formatted markdown report
        """
        if not test_cases:
            return "### 📋 Test Generation\n\nNo new test cases needed or generated.\n"
        
        report = f"### 📋 Test Generation\n\n"
        report += f"Generated {len(test_cases)} new test case(s):\n\n"
        
        for i, test in enumerate(test_cases, 1):
            report += f"**Test {i}:** {test.get('description', 'Test case')}\n"
            report += f"- **File:** `{test.get('file', 'unknown')}`\n"
            report += f"- **Targets:** `{test.get('target_file', 'unknown')}`\n\n"
        
        report += "_Generated by CodeCraft AI TestAgent_\n"
        
        return report
