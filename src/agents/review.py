"""
ReviewAgent - Analyzes code for logic, security, and style issues
"""

import os
import json
import structlog
import google.generativeai as genai
from typing import Dict, Any, List
from pathlib import Path

logger = structlog.get_logger(__name__)


class ReviewAgent:
    """Agent responsible for code review analysis"""

    def __init__(self):
        """Initialize ReviewAgent"""
        self.logger = structlog.get_logger(self.__class__.__name__)
        
        # Initialize Gemini API
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)

    def analyze_code(self, pr_diff: str, changed_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze code for logic, security, and style issues.

        Args:
            pr_diff: Git diff content
            changed_files: List of changed files with metadata

        Returns:
            Review analysis with issues categorized by type
        """
        if not pr_diff or pr_diff.strip() == "":
            self.logger.warning("Empty diff provided")
            return {
                "issues": [],
                "summary": "No changes to review",
                "logic_issues": [],
                "security_issues": [],
                "style_issues": []
            }

        try:
            files_info = json.dumps(changed_files, indent=2)
            
            prompt = f"""Perform a detailed code review on this pull request. Analyze for:
1. Logic issues (bugs, incorrect algorithms, edge cases)
2. Security vulnerabilities (injection, auth, data exposure)
3. Style violations (naming, formatting, best practices)

CHANGED FILES:
{files_info}

GIT DIFF (first 5000 chars):
{pr_diff[:5000]}

Respond in JSON format ONLY:
{{
    "summary": "Brief summary of changes",
    "logic_issues": [
        {{
            "severity": "critical|high|medium|low",
            "file": "filename",
            "line": "approximate line or range",
            "issue": "description",
            "suggestion": "how to fix"
        }}
    ],
    "security_issues": [
        {{
            "severity": "critical|high|medium|low",
            "file": "filename",
            "issue": "description",
            "suggestion": "how to fix"
        }}
    ],
    "style_issues": [
        {{
            "severity": "low|medium",
            "file": "filename",
            "issue": "description",
            "suggestion": "how to fix"
        }}
    ],
    "overall_recommendation": "approve|request_changes",
    "overall_score": 0-100
}}

Return ONLY valid JSON."""

            self.logger.info("Analyzing code with Gemini")
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            
            # Parse response
            response_text = response.text.strip()
            
            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            review_data = json.loads(response_text)
            
            # Count total issues
            total_issues = (
                len(review_data.get("logic_issues", [])) +
                len(review_data.get("security_issues", [])) +
                len(review_data.get("style_issues", []))
            )
            
            self.logger.info(
                "Code review completed",
                logic_issues=len(review_data.get("logic_issues", [])),
                security_issues=len(review_data.get("security_issues", [])),
                style_issues=len(review_data.get("style_issues", [])),
                recommendation=review_data.get("overall_recommendation"),
                score=review_data.get("overall_score")
            )
            
            return review_data

        except Exception as e:
            self.logger.error("Code review failed", error=str(e))
            return {
                "error": str(e),
                "issues": [],
                "summary": "Review analysis failed",
                "logic_issues": [],
                "security_issues": [],
                "style_issues": [],
                "overall_recommendation": "review_failed"
            }

    def generate_review_comment(self, review: Dict[str, Any]) -> str:
        """
        Generate a GitHub comment from review analysis.

        Args:
            review: Review analysis dictionary

        Returns:
            Formatted markdown comment
        """
        comment = "## 🔍 Code Review Analysis\n\n"
        
        # Summary
        comment += f"**Summary:** {review.get('summary', 'No summary')}\n\n"
        
        # Overall score
        score = review.get('overall_score', 0)
        comment += f"**Code Quality Score:** {score}/100\n\n"
        
        # Logic Issues
        logic_issues = review.get('logic_issues', [])
        if logic_issues:
            comment += "### ❌ Logic Issues\n"
            for issue in logic_issues:
                severity = issue.get('severity', 'unknown').upper()
                comment += f"- **[{severity}]** {issue.get('file', 'unknown')}: {issue.get('issue', '')}\n"
                comment += f"  > Fix: {issue.get('suggestion', '')}\n\n"
        
        # Security Issues
        security_issues = review.get('security_issues', [])
        if security_issues:
            comment += "### 🔐 Security Issues\n"
            for issue in security_issues:
                severity = issue.get('severity', 'unknown').upper()
                comment += f"- **[{severity}]** {issue.get('file', 'unknown')}: {issue.get('issue', '')}\n"
                comment += f"  > Fix: {issue.get('suggestion', '')}\n\n"
        
        # Style Issues
        style_issues = review.get('style_issues', [])
        if style_issues:
            comment += "### 📝 Style Issues\n"
            for issue in style_issues[:5]:  # Limit to 5 style issues
                comment += f"- {issue.get('file', 'unknown')}: {issue.get('issue', '')}\n"
            if len(style_issues) > 5:
                comment += f"- ... and {len(style_issues) - 5} more style issues\n\n"
        
        # Recommendation
        recommendation = review.get('overall_recommendation', 'unknown').replace('_', ' ').title()
        comment += f"\n**Recommendation:** {recommendation}\n\n"
        
        comment += "_Generated by CodeCraft AI ReviewAgent_"
        
        return comment
