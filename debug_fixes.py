#!/usr/bin/env python3
"""Debug script to see what fixes Gemini is generating"""

import json
import sys
from pathlib import Path
from src.agents.writer import WriterAgent
from src.utils.github_helper import GitHubAPIWrapper

# Get PR diff
github = GitHubAPIWrapper()
pr_diff = github.fetch_pr_diff("0xIta3hi", "codecraft-test", 2)

# Analyze
writer = WriterAgent()
fixes = writer.analyze_and_fix(pr_diff, "../codecraft-test/")

# Print
for i, fix in enumerate(fixes):
    print(f"\n{'='*60}")
    print(f"FIX {i+1}: {fix.get('file_path')}")
    print(f"{'='*60}")
    print(f"Issue: {fix.get('issue', 'N/A')}")
    print(f"\nCode ({len(fix.get('new_code', ''))} chars):")
    print("-" * 40)
    print(fix.get('new_code', '')[:500])
    print("-" * 40)
