"""
Main Orchestrator / Dispatcher

This is the entry point for the GitHub Action. Its job is to:
1. Read the user's command (fix, review, test, analyze)
2. Authenticate the request
3. Call the agents in the correct sequential order
4. Handle exception logging and write output.json
"""

import os
import sys
import json
import argparse
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = structlog.get_logger(__name__)


class CommandType(Enum):
    """Supported command types"""
    FIX = "fix"
    REVIEW = "review"
    TEST = "test"
    ANALYZE = "analyze"
    CUSTOM = "custom"


@dataclass
class ExecutionContext:
    """Execution context for a command"""
    command: CommandType
    owner: str
    repo: str
    pr_number: int
    repo_path: str
    user_id: Optional[str] = None
    custom_prompt: Optional[str] = None
    dry_run: bool = False
    verbose: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "command": self.command.value,
            "owner": self.owner,
            "repo": self.repo,
            "pr_number": self.pr_number,
            "repo_path": self.repo_path,
            "user_id": self.user_id,
            "custom_prompt": self.custom_prompt,
            "dry_run": self.dry_run,
            "verbose": self.verbose
        }


@dataclass
class ExecutionResult:
    """Result of command execution"""
    success: bool
    command: str
    output: Dict[str, Any]
    error: Optional[str] = None
    timestamp: str = None
    duration_seconds: float = 0

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class Orchestrator:
    """
    Main orchestrator that coordinates all agents and tools.
    Handles command routing, authentication, and output generation.
    """

    def __init__(self):
        """Initialize the orchestrator"""
        self.logger = structlog.get_logger(__name__)
        self._validate_environment()
        self.results: List[ExecutionResult] = []

    def _validate_environment(self) -> None:
        """Validate that all required environment variables are set"""
        required_vars = ["GITHUB_TOKEN", "GEMINI_API_KEY"]
        missing = [var for var in required_vars if not os.getenv(var)]

        if missing:
            self.logger.error(
                "Missing environment variables",
                missing=missing
            )
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        self.logger.info("Environment validation passed")

    def authenticate(self, context: ExecutionContext) -> bool:
        """
        Authenticate the request.

        Args:
            context: Execution context

        Returns:
            True if authentication succeeds
        """
        self.logger.info(
            "Authenticating request",
            owner=context.owner,
            repo=context.repo,
            user_id=context.user_id
        )

        # Validate GitHub token can access the repo
        try:
            from src.utils.github_helper import GitHubAPIWrapper
            github = GitHubAPIWrapper()
            
            if not github.verify_token():
                self.logger.error("Invalid GitHub token")
                return False

            # Verify user can access repo
            repo_info = github.get_repo_info(context.owner, context.repo)
            self.logger.info(
                "Repository access verified",
                repo=repo_info.get("full_name")
            )
            return True

        except Exception as e:
            self.logger.error("Authentication failed", error=str(e))
            return False

    # ==================== Command Handlers ====================

    def handle_fix_command(self, context: ExecutionContext) -> ExecutionResult:
        """
        Handle 'fix' command: Analyze PR, apply fixes, and verify with tests.

        Args:
            context: Execution context

        Returns:
            ExecutionResult
        """
        start_time = datetime.now()
        self.logger.info("Handling FIX command", pr_number=context.pr_number)

        try:
            from src.utils.github_helper import GitHubAPIWrapper
            from src.agents.writer import WriterAgent

            github = GitHubAPIWrapper()
            writer = WriterAgent()
            output = {}

            # Step 1: Check if it's a PR
            self.logger.info("Step 1: Verifying PR exists")
            pr_details = github.fetch_pr_details(
                context.owner,
                context.repo,
                context.pr_number
            )
            if not pr_details or not pr_details.get("id"):
                self.logger.warning("Not a valid PR")
                comment = f"❌ PR #{context.pr_number} does not exist or is not accessible."
                github.post_comment(context.owner, context.repo, context.pr_number, comment)
                output["pr_valid"] = False
                output["comment"] = comment

                return ExecutionResult(
                    success=False,
                    command="fix",
                    output=output,
                    error="Invalid or inaccessible PR",
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )

            output["pr_valid"] = True
            output["pr_details"] = pr_details

            # Step 2: Fetch PR diff
            self.logger.info("Step 2: Fetching PR diff")
            pr_diff = github.fetch_pr_diff(
                context.owner,
                context.repo,
                context.pr_number
            )
            output["diff_size"] = len(pr_diff)

            # Step 2.5: Check if diff is empty
            if not pr_diff or pr_diff.strip() == "":
                self.logger.warning("PR diff is empty")
                comment = "📝 No changes detected in this PR. Nothing to fix."
                github.post_comment(context.owner, context.repo, context.pr_number, comment)
                output["diff_empty"] = True
                output["comment"] = comment

                return ExecutionResult(
                    success=False,
                    command="fix",
                    output=output,
                    error="Empty PR diff",
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )

            # Step 3: Get changed files
            self.logger.info("Step 3: Getting changed files")
            changed_files = github.get_pr_files(
                context.owner,
                context.repo,
                context.pr_number
            )
            output["changed_files"] = changed_files

            # Step 4: Analyze and generate fixes
            self.logger.info("Step 4: Analyzing and generating fixes")
            fixes = writer.analyze_and_fix(pr_diff)
            output["fixes_found"] = len(fixes) > 0
            output["fixes"] = fixes

            if not fixes:
                self.logger.warning("No fixes found")
                comment = "✅ Code analysis complete. No issues found that require fixing."
                github.post_comment(context.owner, context.repo, context.pr_number, comment)
                output["comment"] = comment

                return ExecutionResult(
                    success=True,
                    command="fix",
                    output=output,
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )

            # Step 5: Apply fixes and verify
            self.logger.info("Step 5: Applying fixes and verifying with tests")
            all_fixes_successful = True
            successful_fixes = []
            failed_fixes = []

            for fix in fixes:
                file_path = fix.get("file_path")
                new_code = fix.get("new_code")

                self.logger.info("Applying fix", file=file_path)
                verify_success, error_logs = writer.apply_fix_and_verify(file_path, new_code)

                if verify_success:
                    self.logger.info("Fix verified successfully", file=file_path)
                    successful_fixes.append(fix)
                else:
                    self.logger.warning("Fix verification failed", file=file_path, error=error_logs)
                    all_fixes_successful = False
                    failed_fixes.append({
                        "file": file_path,
                        "error": error_logs,
                        "fix": fix
                    })

            # Step 6: Push successful fixes (if any)
            if successful_fixes and not context.dry_run:
                self.logger.info("Step 6: Pushing verified fixes")
                pr_branch = pr_details.get("head", {}).get("ref")

                if pr_branch:
                    try:
                        push_result = github.push_file(
                            context.owner,
                            context.repo,
                            pr_branch,
                            context.repo_path,
                            "Apply AI-verified fixes"
                        )
                        output["push_result"] = push_result
                        output["fixes_pushed"] = len(successful_fixes)

                        # Step 7: Post success comment
                        self.logger.info("Step 7: Posting success comment")
                        success_comment = (
                            f"✅ **AI Fix Applied Successfully**\n\n"
                            f"Applied {len(successful_fixes)} fix(es) to {', '.join([f['file_path'] for f in successful_fixes])}\n\n"
                            f"All tests passed!"
                        )
                        github.post_comment(context.owner, context.repo, context.pr_number, success_comment)
                        output["comment"] = success_comment
                        output["fix_status"] = "success"

                    except Exception as push_error:
                        self.logger.error("Push failed", error=str(push_error))
                        output["push_error"] = str(push_error)

            # Step 8: Post failure comment for failed fixes
            if failed_fixes:
                self.logger.warning(f"Step 8: {len(failed_fixes)} fix(es) failed verification")
                failure_details = "### 🚨 Fix Verification Failed\n\nThe following fixes failed test verification:\n\n"

                for failed in failed_fixes:
                    failure_details += f"**File:** `{failed['file']}`\n\n"
                    failure_details += "**Test Output:**\n```\n"
                    failure_details += failed['error'] if failed['error'] else "Unknown error"
                    failure_details += "\n```\n\n"

                failure_comment = (
                    f"❌ **AI Fix Failed Verification**\n\n"
                    f"{failure_details}\n"
                    f"Failed fixes were **not applied** and code was reverted to original state."
                )
                github.post_comment(context.owner, context.repo, context.pr_number, failure_comment)
                output["comment"] = failure_comment
                output["fix_status"] = "failed_verification"

            if not successful_fixes and failed_fixes:
                return ExecutionResult(
                    success=False,
                    command="fix",
                    output=output,
                    error="All fixes failed verification",
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )

            duration = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                success=True,
                command="fix",
                output=output,
                duration_seconds=duration
            )

        except Exception as e:
            self.logger.error("Fix command failed", error=str(e), exc_info=True)
            return ExecutionResult(
                success=False,
                command="fix",
                output={},
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )

    def handle_review_command(self, context: ExecutionContext) -> ExecutionResult:
        """
        Handle 'review' command: Review PR and post comments.

        Args:
            context: Execution context

        Returns:
            ExecutionResult
        """
        start_time = datetime.now()
        self.logger.info("Handling REVIEW command", pr_number=context.pr_number)

        try:
            from src.utils.github_helper import GitHubAPIWrapper

            github = GitHubAPIWrapper()
            output = {}

            # Step 1: Fetch PR details
            self.logger.info("Step 1: Fetching PR details")
            pr_details = github.fetch_pr_details(
                context.owner,
                context.repo,
                context.pr_number
            )
            output["pr_details"] = pr_details

            # Step 2: Fetch PR diff
            self.logger.info("Step 2: Fetching PR diff")
            pr_diff = github.fetch_pr_diff(
                context.owner,
                context.repo,
                context.pr_number
            )

            # Step 3: Get changed files
            self.logger.info("Step 3: Getting changed files")
            changed_files = github.get_pr_files(
                context.owner,
                context.repo,
                context.pr_number
            )
            output["changed_files_count"] = len(changed_files)

            # Step 4: Analyze code with Claude
            self.logger.info("Step 4: Analyzing code with Claude")
            review = self._review_code_with_claude(pr_diff, changed_files)
            output["review"] = review

            # Step 5: Post review comment
            if not context.dry_run:
                self.logger.info("Step 5: Posting review comment")
                comment = self._generate_review_comment(review)
                comment_result = github.post_comment(
                    context.owner,
                    context.repo,
                    context.pr_number,
                    comment
                )
                output["comment_posted"] = comment_result
            else:
                self.logger.info("Dry-run mode: Skipping comment")
                output["dry_run"] = True

            duration = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                success=True,
                command="review",
                output=output,
                duration_seconds=duration
            )

        except Exception as e:
            self.logger.error("Review command failed", error=str(e), exc_info=True)
            return ExecutionResult(
                success=False,
                command="review",
                output={},
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )

    def handle_test_command(self, context: ExecutionContext) -> ExecutionResult:
        """
        Handle 'test' command: Run tests on the PR.

        Args:
            context: Execution context

        Returns:
            ExecutionResult
        """
        start_time = datetime.now()
        self.logger.info("Handling TEST command", pr_number=context.pr_number)

        try:
            from src.utils.github_helper import GitHubAPIWrapper
            import subprocess

            github = GitHubAPIWrapper()
            output = {}

            # Step 1: Fetch PR details
            self.logger.info("Step 1: Fetching PR details")
            pr_details = github.fetch_pr_details(
                context.owner,
                context.repo,
                context.pr_number
            )
            output["pr_details"] = pr_details

            # Step 2: Clone/pull repo
            self.logger.info("Step 2: Setting up repository")
            if not os.path.exists(context.repo_path):
                github.clone_repo(
                    context.owner,
                    context.repo,
                    context.repo_path
                )
            else:
                self.logger.info("Repository already exists, pulling latest")

            # Step 3: Run tests
            self.logger.info("Step 3: Running tests")
            test_result = self._run_tests(context.repo_path)
            output["test_results"] = test_result

            # Step 4: Post results comment
            if not context.dry_run:
                self.logger.info("Step 4: Posting test results")
                comment = self._generate_test_results_comment(test_result)
                comment_result = github.post_comment(
                    context.owner,
                    context.repo,
                    context.pr_number,
                    comment
                )
                output["comment_posted"] = comment_result
            else:
                self.logger.info("Dry-run mode: Skipping comment")
                output["dry_run"] = True

            duration = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                success=test_result.get("passed", False),
                command="test",
                output=output,
                duration_seconds=duration
            )

        except Exception as e:
            self.logger.error("Test command failed", error=str(e), exc_info=True)
            return ExecutionResult(
                success=False,
                command="test",
                output={},
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )

    def handle_analyze_command(self, context: ExecutionContext) -> ExecutionResult:
        """
        Handle 'analyze' command: Analyze code without making changes.

        Args:
            context: Execution context

        Returns:
            ExecutionResult
        """
        start_time = datetime.now()
        self.logger.info("Handling ANALYZE command", pr_number=context.pr_number)

        try:
            from src.utils.github_helper import GitHubAPIWrapper

            github = GitHubAPIWrapper()
            output = {}

            # Step 1: Fetch PR diff
            self.logger.info("Step 1: Fetching PR diff")
            pr_diff = github.fetch_pr_diff(
                context.owner,
                context.repo,
                context.pr_number
            )

            # Step 2: Get changed files
            self.logger.info("Step 2: Getting changed files")
            changed_files = github.get_pr_files(
                context.owner,
                context.repo,
                context.pr_number
            )

            # Step 3: Analyze with Claude
            self.logger.info("Step 3: Analyzing code")
            analysis = self._analyze_code_with_claude(pr_diff, changed_files)
            output["analysis"] = analysis

            duration = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                success=True,
                command="analyze",
                output=output,
                duration_seconds=duration
            )

        except Exception as e:
            self.logger.error("Analyze command failed", error=str(e), exc_info=True)
            return ExecutionResult(
                success=False,
                command="analyze",
                output={},
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )

    # ==================== Helper Methods ====================

    def _analyze_code_with_gemini(
        self,
        diff: str,
        files: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze code using Google Gemini API.

        Args:
            diff: PR diff
            files: Changed files

        Returns:
            Analysis result
        """
        try:
            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            prompt = f"""
            Analyze this pull request diff and the changed files.
            
            Changed files:
            {json.dumps(files, indent=2)}
            
            Diff:
            {diff[:4000]}  # Limit to 4000 chars
            
            Provide analysis on:
            1. Code quality issues
            2. Potential bugs
            3. Performance concerns
            4. Security issues
            5. Best practice violations
            """

            response = model.generate_content(prompt)
            analysis_text = response.text

            return {
                "summary": analysis_text[:500],
                "full_analysis": analysis_text,
                "model": "gemini-2.0-flash",
                "usage": {
                    "input_tokens": response.usage_metadata.prompt_token_count,
                    "output_tokens": response.usage_metadata.candidates_token_count
                }
            }

        except Exception as e:
            self.logger.error("Gemini analysis failed", error=str(e))
            return {"error": str(e), "summary": "Analysis failed"}

    def _review_code_with_claude(
        self,
        diff: str,
        files: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Review code using Google Gemini API"""
        try:
            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            prompt = f"""
            Perform a code review on this pull request.
            
            Files changed: {len(files)}
            {json.dumps(files, indent=2)}
            
            Diff (first 4000 chars):
            {diff[:4000]}
            
            Provide a detailed code review with:
            1. Positive aspects
            2. Issues to fix
            3. Suggestions for improvement
            4. Overall recommendation (approve/request changes)
            
            Format as structured feedback.
            """

            response = model.generate_content(prompt)
            review_text = response.text

            return {
                "review": review_text,
                "model": "gemini-1.5-pro",
                "usage": {
                    "input_tokens": response.usage_metadata.prompt_token_count,
                    "output_tokens": response.usage_metadata.candidates_token_count
                }
            }

        except Exception as e:
            self.logger.error("Gemini review failed", error=str(e))
            return {"error": str(e), "review": "Review failed"}

    def _generate_fixes(
        self,
        analysis: Dict[str, Any],
        diff: str
    ) -> List[Dict[str, Any]]:
        """Generate fixes based on analysis"""
        try:
            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            prompt = f"""
            Based on this code analysis and diff, generate specific fixes.
            
            Analysis:
            {analysis.get('full_analysis', '')}
            
            Generate fixes in format:
            [FIX]
            File: <filename>
            Issue: <issue description>
            Fix: <code fix>
            [/FIX]
            
            Maximum 5 fixes.
            """

            response = model.generate_content(prompt)

            # Parse response to extract fixes
            fixes_text = response.text
            fixes = [
                {"description": fix.strip()}
                for fix in fixes_text.split("[FIX]")[1:]
                if fix.strip()
            ]

            return fixes

        except Exception as e:
            self.logger.error("Generate fixes failed", error=str(e))
            return []

    def _run_tests(self, repo_path: str) -> Dict[str, Any]:
        """Run pytest on the repository"""
        try:
            import subprocess

            result = subprocess.run(
                ["pytest", "tests/", "-v", "--tb=short"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300
            )

            return {
                "passed": result.returncode == 0,
                "return_code": result.returncode,
                "stdout": result.stdout[-2000:],  # Last 2000 chars
                "stderr": result.stderr[-2000:]
            }

        except subprocess.TimeoutExpired:
            return {"passed": False, "error": "Test timeout"}
        except Exception as e:
            self.logger.error("Test execution failed", error=str(e))
            return {"passed": False, "error": str(e)}

    def _generate_fix_summary_comment(
        self,
        analysis: Dict[str, Any],
        fixes: List[Dict[str, Any]]
    ) -> str:
        """Generate a summary comment for fixes"""
        comment = "## AI Code Analysis & Fixes\n\n"
        comment += f"**Analysis Summary:**\n{analysis.get('summary', 'N/A')}\n\n"
        comment += f"**Fixes Applied:** {len(fixes)}\n"
        for i, fix in enumerate(fixes, 1):
            comment += f"- {fix.get('description', 'Fix ' + str(i))}\n"
        comment += "\n_Generated by CodeCraft AI_"
        return comment

    def _generate_review_comment(self, review: Dict[str, Any]) -> str:
        """Generate a review comment"""
        comment = "## Code Review\n\n"
        comment += review.get('review', 'Review completed')
        comment += "\n\n_Generated by CodeCraft AI_"
        return comment

    def _generate_test_results_comment(self, results: Dict[str, Any]) -> str:
        """Generate a test results comment"""
        status = "PASSED" if results.get('passed') else "FAILED"
        comment = f"## {status} Test Results\n\n"
        comment += f"```\n{results.get('stdout', 'No output')}\n```"
        if results.get('stderr'):
            comment += f"\n**Errors:**\n```\n{results['stderr']}\n```"
        comment += "\n\n_Generated by CodeCraft AI_"
        return comment

    # ==================== Main Execution ====================

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """
        Execute a command with the given context.

        Args:
            context: Execution context

        Returns:
            ExecutionResult
        """
        self.logger.info("Starting execution", command=context.command.value)

        # Authenticate
        if not self.authenticate(context):
            return ExecutionResult(
                success=False,
                command=context.command.value,
                output={},
                error="Authentication failed"
            )

        # Route to appropriate handler
        handlers = {
            CommandType.FIX: self.handle_fix_command,
            CommandType.REVIEW: self.handle_review_command,
            CommandType.TEST: self.handle_test_command,
            CommandType.ANALYZE: self.handle_analyze_command,
        }

        handler = handlers.get(context.command)
        if not handler:
            return ExecutionResult(
                success=False,
                command=context.command.value,
                output={},
                error=f"Unknown command: {context.command.value}"
            )

        result = handler(context)
        self.results.append(result)
        return result

    def write_output(self, result: ExecutionResult, output_file: str = "output.json") -> None:
        """
        Write execution result to output file.

        Args:
            result: ExecutionResult to write
            output_file: Path to output file
        """
        try:
            output = {
                "timestamp": datetime.now().isoformat(),
                "results": [r.to_dict() for r in self.results],
                "final_status": "success" if result.success else "failure"
            }

            Path(output_file).write_text(json.dumps(output, indent=2))
            self.logger.info("Output written", file=output_file)

        except Exception as e:
            self.logger.error("Failed to write output", error=str(e))


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="CodeCraft AI - GitHub PR Analysis & Automation"
    )
    parser.add_argument(
        "command",
        choices=["fix", "review", "test", "analyze"],
        help="Command to execute"
    )
    parser.add_argument("--owner", required=True, help="Repository owner")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--pr-number", type=int, required=True, help="PR number")
    parser.add_argument("--repo-path", required=True, help="Path to repository")
    parser.add_argument("--user-id", help="User ID")
    parser.add_argument("--custom-prompt", help="Custom prompt for analysis")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (no commits/pushes)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging"
    )
    parser.add_argument(
        "--output",
        default="output.json",
        help="Output file path"
    )

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        structlog.configure(
            wrapper_class=structlog.BoundLogger,
            processors=[
                structlog.processors.JSONRenderer()
            ]
        )

    try:
        # Create execution context
        context = ExecutionContext(
            command=CommandType(args.command),
            owner=args.owner,
            repo=args.repo,
            pr_number=args.pr_number,
            repo_path=args.repo_path,
            user_id=args.user_id,
            custom_prompt=args.custom_prompt,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        # Create and run orchestrator
        orchestrator = Orchestrator()
        result = orchestrator.execute(context)

        # Write output
        orchestrator.write_output(result, args.output)

        # Exit with appropriate code
        sys.exit(0 if result.success else 1)

    except Exception as e:
        logger.error("Orchestrator failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
