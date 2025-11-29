"""
Quick test script to verify Neo4j memory system is working.

Run this after starting Neo4j to ensure the connection is properly configured.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.memory import get_memory_manager, close_memory_manager
from src.utils.memory_integration import MemoryIntegration


def test_neo4j_connection():
    """Test basic Neo4j connection"""
    print("🔍 Testing Neo4j Connection...")
    try:
        memory = get_memory_manager()
        print("✅ Connection successful!")
        return memory
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None


def test_store_pr(memory):
    """Test storing a PR"""
    print("\n📝 Testing PR Storage...")
    try:
        memory.store_pr(
            pr_number=1,
            owner="0xIta3hi",
            repo="codecraft-ai",
            title="Test PR",
            author="test_user",
            url="https://github.com/0xIta3hi/codecraft-ai/pull/1"
        )
        print("✅ PR stored successfully!")
        return True
    except Exception as e:
        print(f"❌ PR storage failed: {e}")
        return False


def test_store_analysis(memory):
    """Test storing analysis"""
    print("\n📊 Testing Analysis Storage...")
    try:
        analysis = {
            "summary": "Test analysis",
            "issues_found": 3,
            "quality_score": 7.5
        }
        analysis_id = memory.store_pr_analysis(
            pr_number=1,
            repo="codecraft-ai",
            owner="0xIta3hi",
            analysis=analysis
        )
        print(f"✅ Analysis stored! ID: {analysis_id}")
        return True
    except Exception as e:
        print(f"❌ Analysis storage failed: {e}")
        return False


def test_store_decision(memory):
    """Test storing a decision"""
    print("\n🤖 Testing Decision Storage...")
    try:
        decision_id = memory.store_decision(
            decision_id="test-decision-001",
            pr_number=1,
            owner="0xIta3hi",
            repo="codecraft-ai",
            decision_type="apply_fix",
            reasoning="Test decision",
            outcome={"status": "success"},
            tags=["test"]
        )
        print(f"✅ Decision stored! ID: {decision_id}")
        return True
    except Exception as e:
        print(f"❌ Decision storage failed: {e}")
        return False


def test_store_fix(memory):
    """Test storing a fix"""
    print("\n🔧 Testing Fix Storage...")
    try:
        fix_id = memory.store_fix(
            fix_id="test-fix-001",
            pr_number=1,
            owner="0xIta3hi",
            repo="codecraft-ai",
            file_path="src/test.py",
            issue="Test issue",
            fix_code="print('fixed')",
            applied=True
        )
        print(f"✅ Fix stored! ID: {fix_id}")
        return True
    except Exception as e:
        print(f"❌ Fix storage failed: {e}")
        return False


def test_query_history(memory):
    """Test querying PR history"""
    print("\n📖 Testing Query PR History...")
    try:
        history = memory.get_pr_history(
            pr_number=1,
            owner="0xIta3hi",
            repo="codecraft-ai"
        )
        print(f"✅ Query successful!")
        print(f"   - PR: {history.get('pr', {})}")
        print(f"   - Analyses: {len(history.get('analyses', []))}")
        print(f"   - Decisions: {len(history.get('decisions', []))}")
        print(f"   - Fixes: {len(history.get('fixes', []))}")
        return True
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return False


def test_stats(memory):
    """Test getting statistics"""
    print("\n📈 Testing Repository Statistics...")
    try:
        stats = memory.get_pr_statistics(
            owner="0xIta3hi",
            repo="codecraft-ai"
        )
        print(f"✅ Statistics retrieved!")
        print(f"   - Total PRs: {stats.get('total_prs', 0)}")
        print(f"   - Total Analyses: {stats.get('total_analyses', 0)}")
        print(f"   - Total Decisions: {stats.get('total_decisions', 0)}")
        print(f"   - Total Fixes: {stats.get('total_fixes', 0)}")
        return True
    except Exception as e:
        print(f"❌ Statistics failed: {e}")
        return False


def test_memory_integration(memory):
    """Test memory integration helper"""
    print("\n🔗 Testing Memory Integration Helper...")
    try:
        integration = MemoryIntegration(memory)
        
        # Test store PR workflow
        integration.store_pr_workflow(
            owner="0xIta3hi",
            repo="codecraft-ai",
            pr_number=2,
            pr_title="Integration Test PR",
            pr_author="test_user",
            pr_url="https://github.com/0xIta3hi/codecraft-ai/pull/2"
        )
        
        # Test get context
        context = integration.get_pr_context(
            owner="0xIta3hi",
            repo="codecraft-ai",
            pr_number=1
        )
        
        print("✅ Memory integration working!")
        return True
    except Exception as e:
        print(f"❌ Memory integration failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 CodeCraft AI - Neo4j Memory System Test Suite")
    print("=" * 60)

    # Test connection
    memory = test_neo4j_connection()
    if not memory:
        print("\n❌ Cannot proceed without valid Neo4j connection")
        print("\nMake sure:")
        print("  1. Neo4j is running (neo4j start)")
        print("  2. .env has correct NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        return False

    # Run tests
    tests = [
        ("PR Storage", lambda: test_store_pr(memory)),
        ("Analysis Storage", lambda: test_store_analysis(memory)),
        ("Decision Storage", lambda: test_store_decision(memory)),
        ("Fix Storage", lambda: test_store_fix(memory)),
        ("Query History", lambda: test_query_history(memory)),
        ("Statistics", lambda: test_stats(memory)),
        ("Memory Integration", lambda: test_memory_integration(memory))
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {(passed / (passed + failed) * 100):.1f}%")

    # Cleanup
    close_memory_manager()
    print("\n✅ Memory manager closed")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
