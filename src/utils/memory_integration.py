"""
Memory Integration Helper

Provides utilities for integrating Neo4j memory manager with the orchestrator.
Simplifies common operations like storing analysis results and decisions.
"""

from typing import Optional, Dict, Any, List
import uuid
from datetime import datetime

import structlog
from src.memory import Neo4jMemoryManager

logger = structlog.get_logger(__name__)


class MemoryIntegration:
    """Helper class to integrate memory operations with the orchestrator"""

    def __init__(self, memory_manager: Neo4jMemoryManager):
        """
        Initialize memory integration.

        Args:
            memory_manager: Neo4jMemoryManager instance
        """
        self.memory = memory_manager
        self.logger = structlog.get_logger(__name__)

    def store_pr_workflow(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str
    ) -> None:
        """
        Store PR information in the graph.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            pr_title: PR title
            pr_author: PR author
            pr_url: PR URL
        """
        try:
            self.memory.store_pr(
                pr_number=pr_number,
                owner=owner,
                repo=repo,
                title=pr_title,
                author=pr_author,
                url=pr_url
            )
            self.logger.info("PR stored in memory", pr_number=pr_number)
        except Exception as e:
            self.logger.error("Failed to store PR in memory", error=str(e))

    def store_analysis_workflow(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        analysis: Dict[str, Any]
    ) -> str:
        """
        Store analysis results in the graph.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            analysis: Analysis result dictionary

        Returns:
            Analysis ID
        """
        try:
            analysis_id = self.memory.store_pr_analysis(
                pr_number=pr_number,
                repo=repo,
                owner=owner,
                analysis=analysis
            )
            self.logger.info(
                "Analysis stored in memory",
                analysis_id=analysis_id
            )
            return analysis_id
        except Exception as e:
            self.logger.error("Failed to store analysis in memory", error=str(e))
            return ""

    def store_fixes_workflow(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        fixes: List[Dict[str, Any]],
        applied: bool = False
    ) -> List[str]:
        """
        Store generated/applied fixes in the graph.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            fixes: List of fix dictionaries
            applied: Whether fixes were applied

        Returns:
            List of fix IDs
        """
        fix_ids = []
        try:
            for i, fix in enumerate(fixes):
                fix_id = f"{owner}/{repo}/pr-{pr_number}/fix-{i}-{uuid.uuid4().hex[:8]}"
                self.memory.store_fix(
                    fix_id=fix_id,
                    pr_number=pr_number,
                    owner=owner,
                    repo=repo,
                    file_path=fix.get("file", "unknown"),
                    issue=fix.get("issue", ""),
                    fix_code=fix.get("code", fix.get("description", "")),
                    applied=applied
                )
                fix_ids.append(fix_id)

            self.logger.info(
                "Fixes stored in memory",
                fix_count=len(fix_ids)
            )
            return fix_ids
        except Exception as e:
            self.logger.error("Failed to store fixes in memory", error=str(e))
            return fix_ids

    def store_decision_workflow(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        decision_type: str,
        reasoning: str,
        outcome: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Store a decision in the graph.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            decision_type: Type of decision
            reasoning: Reasoning behind the decision
            outcome: Optional outcome information
            tags: Optional tags for the decision

        Returns:
            Decision ID
        """
        try:
            decision_id = f"{owner}/{repo}/pr-{pr_number}/decision-{uuid.uuid4().hex[:8]}"
            self.memory.store_decision(
                decision_id=decision_id,
                pr_number=pr_number,
                owner=owner,
                repo=repo,
                decision_type=decision_type,
                reasoning=reasoning,
                outcome=outcome,
                tags=tags
            )
            self.logger.info(
                "Decision stored in memory",
                decision_id=decision_id
            )
            return decision_id
        except Exception as e:
            self.logger.error("Failed to store decision in memory", error=str(e))
            return ""

    def store_conversation_turn_workflow(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        role: str,
        content: str,
        conversation_id: Optional[str] = None
    ) -> str:
        """
        Store a conversation turn in the graph.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            role: Message role (user, assistant, system)
            content: Message content
            conversation_id: Optional conversation ID for grouping

        Returns:
            Message ID
        """
        try:
            msg_id = self.memory.store_conversation_turn(
                pr_number=pr_number,
                owner=owner,
                repo=repo,
                role=role,
                content=content,
                conversation_id=conversation_id
            )
            return msg_id
        except Exception as e:
            self.logger.error(
                "Failed to store conversation turn in memory",
                error=str(e)
            )
            return ""

    def get_pr_context(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> Dict[str, Any]:
        """
        Get complete PR context for decision making.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            PR context dictionary
        """
        try:
            history = self.memory.get_pr_history(pr_number, owner, repo)
            analysis_chain = self.memory.get_analysis_chain(pr_number, owner, repo)
            conversation = self.memory.get_conversation_history(pr_number, owner, repo)

            return {
                "history": history,
                "analysis_chain": analysis_chain,
                "conversation": conversation,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error("Failed to get PR context", error=str(e))
            return {}

    def find_similar_context(
        self,
        file_path: str,
        issue_pattern: str
    ) -> List[Dict[str, Any]]:
        """
        Find similar fixes from past PRs.

        Args:
            file_path: File path pattern
            issue_pattern: Issue pattern to match

        Returns:
            List of similar fixes
        """
        try:
            similar = self.memory.get_similar_fixes(
                file_path=file_path,
                issue_pattern=issue_pattern,
                limit=5
            )
            return similar
        except Exception as e:
            self.logger.error("Failed to find similar context", error=str(e))
            return []

    def get_repository_stats(
        self,
        owner: str,
        repo: str
    ) -> Dict[str, Any]:
        """
        Get statistics for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Statistics dictionary
        """
        try:
            stats = self.memory.get_pr_statistics(owner, repo)
            return stats
        except Exception as e:
            self.logger.error("Failed to get repository stats", error=str(e))
            return {}
