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
            
            prompt = f"""CRITICAL CODE REVIEW: Analyze this PR for ALL possible bugs and flaws. Be AGGRESSIVE in finding issues.

ANALYZE FOR:
1. LOGICAL BUGS: Incorrect conditions, wrong boolean logic, infinite loops, off-by-one errors, impossible states
2. DATA FLOW: Uninitialized vars, null dereference, type errors, wrong conversions, data loss
3. EDGE CASES: Empty inputs, nulls, negative numbers, very large numbers, boundary conditions - what COULD break?
4. ERROR HANDLING: Missing error checks, silent failures, swallowed exceptions, no validation
5. ALGORITHM BUGS: Wrong algorithm choice, inefficient implementations, missing base cases
6. CONCURRENCY: Race conditions, deadlocks, missing locks, wrong synchronization
7. SECURITY: SQL injection, XSS, auth bypass, data exposure, unsafe deserialization
8. MEMORY/PERFORMANCE: Leaks, inefficient loops, N+1 problems, large object allocations
9. API MISUSE: Wrong function calls, incorrect parameter usage, deprecated methods
10. BUSINESS LOGIC: Does this actually solve the problem? Does it match requirements?

CHANGED FILES:
{files_info}

GIT DIFF:
{pr_diff[:5000]}

RESPOND IN THIS JSON FORMAT ONLY:
{{
    "summary": "What does this PR do and what problems exist?",
    "logic_issues": [
        {{
            "severity": "critical|high|medium|low",
            "file": "filename",
            "line": "line or range",
            "issue": "SPECIFIC description - what is wrong and why?",
            "example": "Show example of the bug",
            "suggestion": "How to fix it"
        }}
    ],
    "security_issues": [
        {{
            "severity": "critical|high|medium",
            "file": "filename",
            "issue": "Specific vulnerability",
            "exploit": "How could this be exploited?",
            "suggestion": "Fix"
        }}
    ],
    "style_issues": [
        {{
            "severity": "low|medium",
            "file": "filename",
            "issue": "description",
            "suggestion": "fix"
        }}
    ],
    "edge_cases_at_risk": ["List potential edge cases that could fail"],
    "overall_recommendation": "approve|request_changes|reject",
    "overall_score": "0-100: be harsh"
}}

BE CRITICAL. BE THOROUGH. FIND EVERY BUG. Return ONLY valid JSON."""

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
            
            # Find JSON object in the response
            if "{" in response_text and "}" in response_text:
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}") + 1
                response_text = response_text[start_idx:end_idx]
            
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

        except json.JSONDecodeError as je:
            self.logger.error("JSON parsing failed", error=str(je), response_text=response_text[:500] if 'response_text' in locals() else "")
            return {
                "error": str(je),
                "issues": [],
                "summary": "Review analysis failed - JSON parsing error",
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
