"""
GitHub API Wrapper

Provides clean, reusable methods for talking to GitHub.
Handles authentication and complex API calls.
"""

import os
import subprocess
import json
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

import requests
from github import Github, GithubException, PullRequest, Repository
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GitConfig:
    """Git configuration dataclass"""
    user_name: str
    user_email: str
    repo_path: str


class GitHubAPIWrapper:
    """
    Wrapper for GitHub API interactions.
    Handles authentication, PR operations, and complex API calls.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = "https://api.github.com"
    ):
        """
        Initialize GitHub API wrapper.

        Args:
            token: GitHub personal access token. If None, uses GITHUB_TOKEN env var.
            base_url: Base URL for GitHub API (default: api.github.com)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token not provided. "
                "Set GITHUB_TOKEN environment variable or pass token parameter."
            )

        self.base_url = base_url
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CodeCraft-AI"
        }
        self.github = Github(self.token)
        logger.info("GitHub API wrapper initialized")

    # ==================== Repository Operations ====================

    def get_repo(self, owner: str, repo: str) -> Repository.Repository:
        """
        Get a repository object.

        Args:
            owner: Repository owner username
            repo: Repository name

        Returns:
            GitHub Repository object
        """
        try:
            repository = self.github.get_user(owner).get_repo(repo)
            logger.info("Repository retrieved", owner=owner, repo=repo)
            return repository
        except GithubException as e:
            logger.error("Failed to get repository", error=str(e))
            raise

    def get_repo_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Get repository information.

        Args:
            owner: Repository owner username
            repo: Repository name

        Returns:
            Dictionary with repository info
        """
        try:
            repository = self.get_repo(owner, repo)
            info = {
                "name": repository.name,
                "full_name": repository.full_name,
                "description": repository.description,
                "url": repository.html_url,
                "is_private": repository.private,
                "stars": repository.stargazers_count,
                "forks": repository.forks_count,
                "open_issues": repository.open_issues_count,
                "language": repository.language,
                "topics": repository.topics,
                "default_branch": repository.default_branch
            }
            logger.info("Repository info retrieved", repo=repo)
            return info
        except GithubException as e:
            logger.error("Failed to get repository info", error=str(e))
            raise

    # ==================== Pull Request Operations ====================

    def get_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> PullRequest.PullRequest:
        """
        Get a pull request object.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number

        Returns:
            GitHub PullRequest object
        """
        try:
            repository = self.get_repo(owner, repo)
            pull_request = repository.get_pull(pr_number)
            logger.info("PR retrieved", repo=repo, pr_number=pr_number)
            return pull_request
        except GithubException as e:
            logger.error("Failed to get PR", error=str(e), pr_number=pr_number)
            raise

    def fetch_pr_diff(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> str:
        """
        Fetch the diff for a pull request.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number

        Returns:
            Diff content as string
        """
        try:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
            headers = self.headers.copy()
            headers["Accept"] = "application/vnd.github.v3.diff"

            response = requests.get(url, headers=headers)
            response.raise_for_status()

            logger.info("PR diff fetched", repo=repo, pr_number=pr_number)
            return response.text
        except requests.RequestException as e:
            logger.error("Failed to fetch PR diff", error=str(e))
            raise

    def fetch_pr_details(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> Dict[str, Any]:
        """
        Fetch detailed information about a pull request.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number

        Returns:
            Dictionary with PR details
        """
        try:
            pr = self.get_pr(owner, repo, pr_number)
            details = {
                "number": pr.number,
                "title": pr.title,
                "description": pr.body,
                "state": pr.state,
                "author": pr.user.login,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "head_ref": pr.head.ref,
                "base_ref": pr.base.ref,
                "commits": pr.commits,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
                "url": pr.html_url,
                "mergeable": pr.mergeable,
                "draft": pr.draft
            }
            logger.info("PR details fetched", repo=repo, pr_number=pr_number)
            return details
        except GithubException as e:
            logger.error("Failed to fetch PR details", error=str(e))
            raise

    def get_pr_files(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> List[Dict[str, Any]]:
        """
        Get list of files changed in a pull request.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of file change dictionaries
        """
        try:
            pr = self.get_pr(owner, repo, pr_number)
            files = [
                {
                    "filename": file.filename,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "changes": file.changes,
                    "patch": file.patch if hasattr(file, 'patch') else None
                }
                for file in pr.get_files()
            ]
            logger.info("PR files retrieved", repo=repo, pr_number=pr_number)
            return files
        except GithubException as e:
            logger.error("Failed to get PR files", error=str(e))
            raise

    # ==================== Comments Operations ====================

    def post_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comment: str
    ) -> Dict[str, Any]:
        """
        Post a comment on a pull request.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number
            comment: Comment text

        Returns:
            Dictionary with comment details
        """
        try:
            pr = self.get_pr(owner, repo, pr_number)
            issue_comment = pr.create_issue_comment(comment)

            comment_data = {
                "id": issue_comment.id,
                "body": issue_comment.body,
                "author": issue_comment.user.login,
                "created_at": issue_comment.created_at.isoformat(),
                "url": issue_comment.html_url
            }
            logger.info(
                "Comment posted on PR",
                repo=repo,
                pr_number=pr_number
            )
            return comment_data
        except GithubException as e:
            logger.error("Failed to post comment", error=str(e))
            raise

    def get_pr_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> List[Dict[str, Any]]:
        """
        Get all comments on a pull request.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of comment dictionaries
        """
        try:
            pr = self.get_pr(owner, repo, pr_number)
            comments = [
                {
                    "id": comment.id,
                    "body": comment.body,
                    "author": comment.user.login,
                    "created_at": comment.created_at.isoformat(),
                    "updated_at": comment.updated_at.isoformat(),
                    "url": comment.html_url
                }
                for comment in pr.get_issue_comments()
            ]
            logger.info("PR comments retrieved", repo=repo, pr_number=pr_number)
            return comments
        except GithubException as e:
            logger.error("Failed to get PR comments", error=str(e))
            raise

    def post_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        file_path: str,
        line_number: int,
        comment: str
    ) -> Dict[str, Any]:
        """
        Post a review comment on a specific line of a file in a PR.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number
            commit_id: Commit SHA
            file_path: Path to the file
            line_number: Line number to comment on
            comment: Comment text

        Returns:
            Dictionary with review comment details
        """
        try:
            pr = self.get_pr(owner, repo, pr_number)
            review_comment = pr.create_review_comment(
                body=comment,
                commit_id=commit_id,
                path=file_path,
                line=line_number
            )

            comment_data = {
                "id": review_comment.id,
                "body": review_comment.body,
                "author": review_comment.user.login,
                "path": review_comment.path,
                "line": review_comment.line,
                "url": review_comment.html_url
            }
            logger.info(
                "Review comment posted",
                repo=repo,
                pr_number=pr_number,
                file=file_path
            )
            return comment_data
        except GithubException as e:
            logger.error("Failed to post review comment", error=str(e))
            raise

    # ==================== Git Operations ====================

    def setup_git_config(
        self,
        user_name: str,
        user_email: str,
        repo_path: str
    ) -> GitConfig:
        """
        Setup Git configuration.

        Args:
            user_name: Git user name
            user_email: Git user email
            repo_path: Path to the repository

        Returns:
            GitConfig object
        """
        try:
            subprocess.run(
                ["git", "config", "--global", "user.name", user_name],
                cwd=repo_path,
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "--global", "user.email", user_email],
                cwd=repo_path,
                check=True,
                capture_output=True
            )
            logger.info("Git config setup", user_name=user_name)
            return GitConfig(
                user_name=user_name,
                user_email=user_email,
                repo_path=repo_path
            )
        except subprocess.CalledProcessError as e:
            logger.error("Failed to setup git config", error=str(e))
            raise

    def _run_git_command(
        self,
        command: List[str],
        repo_path: str,
        check: bool = True
    ) -> Tuple[str, str, int]:
        """
        Run a git command and return output.

        Args:
            command: Git command as list of strings
            repo_path: Path to the repository
            check: Whether to raise exception on non-zero exit

        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        try:
            result = subprocess.run(
                command,
                cwd=repo_path,
                check=check,
                capture_output=True,
                text=True
            )
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.CalledProcessError as e:
            logger.error("Git command failed", command=command, error=str(e))
            return e.stdout or "", e.stderr or "", e.returncode

    def create_branch(
        self,
        repo_path: str,
        branch_name: str,
        base_branch: str = "main"
    ) -> bool:
        """
        Create a new git branch.

        Args:
            repo_path: Path to the repository
            branch_name: Name of the new branch
            base_branch: Base branch to create from (default: main)

        Returns:
            True if successful
        """
        try:
            # Fetch latest
            self._run_git_command(["git", "fetch", "origin"], repo_path)

            # Create and checkout branch
            self._run_git_command(
                ["git", "checkout", "-b", branch_name, f"origin/{base_branch}"],
                repo_path
            )
            logger.info("Branch created", branch_name=branch_name)
            return True
        except Exception as e:
            logger.error("Failed to create branch", error=str(e))
            return False

    def commit_changes(
        self,
        repo_path: str,
        files: Optional[List[str]] = None,
        message: str = "AI-generated fixes"
    ) -> bool:
        """
        Commit changes to git.

        Args:
            repo_path: Path to the repository
            files: List of files to commit (None = all changes)
            message: Commit message

        Returns:
            True if successful
        """
        try:
            if files:
                for file in files:
                    self._run_git_command(
                        ["git", "add", file],
                        repo_path
                    )
            else:
                self._run_git_command(["git", "add", "."], repo_path)

            self._run_git_command(
                ["git", "commit", "-m", message],
                repo_path
            )
            logger.info("Changes committed", message=message)
            return True
        except Exception as e:
            logger.error("Failed to commit changes", error=str(e))
            return False

    def push_branch(
        self,
        repo_path: str,
        branch_name: str,
        force: bool = False
    ) -> bool:
        """
        Push branch to remote.

        Args:
            repo_path: Path to the repository
            branch_name: Name of the branch to push
            force: Whether to force push

        Returns:
            True if successful
        """
        try:
            cmd = ["git", "push", "-u", "origin", branch_name]
            if force:
                cmd.insert(2, "-f")

            self._run_git_command(cmd, repo_path)
            logger.info("Branch pushed", branch_name=branch_name)
            return True
        except Exception as e:
            logger.error("Failed to push branch", error=str(e))
            return False

    def push_fix_to_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        repo_path: str,
        files: Optional[List[str]] = None,
        commit_message: str = "Apply AI-generated fixes",
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Push fixes to an existing pull request.
        This is the crucial method that combines Git logic.

        Args:
            owner: Repository owner username
            repo: Repository name
            pr_number: Pull request number
            repo_path: Path to the repository
            files: List of files to commit (None = all changes)
            commit_message: Commit message
            force: Whether to force push

        Returns:
            Dictionary with operation details
        """
        try:
            logger.info("Starting push_fix_to_pr", pr_number=pr_number)

            # Get PR details to know the branch name
            pr = self.get_pr(owner, repo, pr_number)
            branch_name = pr.head.ref

            # Fetch latest changes
            self._run_git_command(["git", "fetch", "origin"], repo_path)

            # Checkout the PR branch
            self._run_git_command(
                ["git", "checkout", branch_name],
                repo_path
            )

            # Commit changes
            if not self.commit_changes(repo_path, files, commit_message):
                return {
                    "success": False,
                    "error": "Failed to commit changes",
                    "pr_number": pr_number
                }

            # Push changes
            if not self.push_branch(repo_path, branch_name, force):
                return {
                    "success": False,
                    "error": "Failed to push changes",
                    "pr_number": pr_number
                }

            logger.info(
                "Fixes pushed to PR",
                pr_number=pr_number,
                branch=branch_name
            )
            return {
                "success": True,
                "pr_number": pr_number,
                "branch": branch_name,
                "commit_message": commit_message,
                "files_modified": files or "all",
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error("Failed to push fix to PR", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "pr_number": pr_number
            }

    def clone_repo(
        self,
        owner: str,
        repo: str,
        destination: str,
        use_ssh: bool = False
    ) -> bool:
        """
        Clone a repository.

        Args:
            owner: Repository owner username
            repo: Repository name
            destination: Path where to clone
            use_ssh: Whether to use SSH instead of HTTPS

        Returns:
            True if successful
        """
        try:
            if use_ssh:
                url = f"git@github.com:{owner}/{repo}.git"
            else:
                url = f"https://github.com/{owner}/{repo}.git"

            self._run_git_command(["git", "clone", url, destination], "/")
            logger.info("Repository cloned", repo=repo, destination=destination)
            return True
        except Exception as e:
            logger.error("Failed to clone repository", error=str(e))
            return False

    # ==================== Issue Operations ====================

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str = "",
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new issue.

        Args:
            owner: Repository owner username
            repo: Repository name
            title: Issue title
            body: Issue description
            labels: List of labels
            assignee: Username to assign to

        Returns:
            Dictionary with issue details
        """
        try:
            repository = self.get_repo(owner, repo)
            issue = repository.create_issue(
                title=title,
                body=body,
                labels=labels or [],
                assignee=assignee
            )

            issue_data = {
                "number": issue.number,
                "title": issue.title,
                "body": issue.body,
                "state": issue.state,
                "url": issue.html_url,
                "created_at": issue.created_at.isoformat()
            }
            logger.info("Issue created", repo=repo, issue_number=issue.number)
            return issue_data
        except GithubException as e:
            logger.error("Failed to create issue", error=str(e))
            raise

    # ==================== Utility Methods ====================

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get authenticated user information.

        Returns:
            Dictionary with user details
        """
        try:
            user = self.github.get_user()
            user_data = {
                "login": user.login,
                "name": user.name,
                "email": user.email,
                "bio": user.bio,
                "followers": user.followers,
                "following": user.following,
                "public_repos": user.public_repos,
                "created_at": user.created_at.isoformat()
            }
            logger.info("User info retrieved", user=user.login)
            return user_data
        except GithubException as e:
            logger.error("Failed to get user info", error=str(e))
            raise

    def verify_token(self) -> bool:
        """
        Verify that the GitHub token is valid.

        Returns:
            True if token is valid
        """
        try:
            self.github.get_user()
            logger.info("Token verified")
            return True
        except GithubException:
            logger.error("Invalid GitHub token")
            return False
