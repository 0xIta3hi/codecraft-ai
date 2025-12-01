# CodeCraft AI 🤖

An intelligent, multi-agent agentic system that automates GitHub code review, testing, and bug fixing using AI. CodeCraft AI analyzes pull requests, identifies bugs, generates tests, and proposes fixes—all autonomously.

## Overview

CodeCraft AI is built on a **sequential multi-agent architecture** where specialized AI agents work together to improve code quality:

1. **ReviewAgent** - Analyzes code for logic, security, and style issues
2. **TestAgent** - Generates comprehensive pytest test cases for uncovered code
3. **WriterAgent** - Detects bugs and generates fixes with self-healing verification

Each agent leverages Google's Gemini 2.0 Flash model with JSON-mode responses for structured, reliable output.

## Features

### 🔍 Code Review
- Aggressive logic issue detection (null checks, off-by-one errors, type mismatches)
- Security vulnerability scanning (injection flaws, unsafe defaults, unsafe deserialization)
- Code style and best practice recommendations
- Categorized issue reporting (logic → security → style)

### 🧪 Autonomous Test Generation
- Automatic pytest test case generation for changed code
- Edge case and boundary condition coverage
- Error handling and exception testing
- Integration point validation

### 🔧 Intelligent Bug Fixing
- Automatic bug detection from PR diffs
- AI-powered code fix generation
- **Self-healing verification**: fixes are tested automatically
- Automatic rollback on test failure
- File backup and safe restoration

### 📊 Architecture Features
- **Sequential agent orchestration** for coordinated analysis
- **Structured JSON output** from all agents for reliable parsing
- **Comprehensive logging** with structlog for debugging
- **GitHub API integration** for PR operations
- **Neo4j memory system** for contextual learning (extensible)

## Installation

### Prerequisites
- Python 3.9+
- GitHub Personal Access Token ([create here](https://github.com/settings/tokens))
- Google Gemini API Key ([get here](https://makersuite.google.com/app/apikey))

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/0xIta3hi/codecraft-ai.git
cd codecraft-ai
```

2. **Create a virtual environment:**
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
Create a `.env` file in the project root:
```env
GITHUB_TOKEN=your_github_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

## Usage

CodeCraft AI is controlled via command-line interface with multiple commands:

### Fix Command
Analyzes PR bugs and generates automated fixes:
```bash
python -m src.main fix \
  --owner <github_username> \
  --repo <repository_name> \
  --pr-number <PR_number> \
  --repo-path <local_repo_path>
```

**Example:**
```bash
python -m src.main fix \
  --owner 0xIta3hi \
  --repo codecraft-test \
  --pr-number 2 \
  --repo-path ../codecraft-test/
```

**Output:**
- Identifies buggy files from PR diff
- Generates fixes with Gemini
- Applies fixes to local files
- Runs pytest to verify fixes
- Logs all changes and test results

### Review Command
Analyzes pull requests for code quality issues:
```bash
python -m src.main review \
  --owner <github_username> \
  --repo <repository_name> \
  --pr-number <PR_number>
```

**Output:**
- Logic issues (null pointer checks, bounds errors, type errors)
- Security vulnerabilities
- Style recommendations
- Severity levels and descriptions

### Test Command
Generates test cases for PR changes:
```bash
python -m src.main test \
  --owner <github_username> \
  --repo <repository_name> \
  --pr-number <PR_number>
```

**Output:**
- Pytest test cases for changed functions
- Edge cases and boundary conditions
- Error handling tests
- Generated test file paths

### Analyze Command
Comprehensive analysis combining all agents:
```bash
python -m src.main analyze \
  --owner <github_username> \
  --repo <repository_name> \
  --pr-number <PR_number>
```

## Architecture

### Directory Structure
```
codecraft-ai/
├── src/
│   ├── main.py                 # Orchestrator & CLI entry point
│   ├── agents/
│   │   ├── review.py          # Code review analysis agent
│   │   ├── test.py            # Test generation agent
│   │   └── writer.py          # Bug fix & code writing agent
│   ├── utils/
│   │   ├── github_helper.py   # GitHub API wrapper
│   │   └── memory_integration.py
│   └── memory/
│       ├── memory_manager.py  # Neo4j integration (planned)
│       └── README.md
├── tests/                       # Test suite
├── logs/                        # Execution logs
├── checkpoints/                 # Agent checkpoints
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

### Agent Components

#### ReviewAgent (`src/agents/review.py`)
**Responsibility:** Code quality analysis
- Scans PR diffs for logic, security, and style issues
- Outputs categorized issue list with severity
- Uses aggressive scanning for comprehensive coverage

**Key Methods:**
- `analyze_code(pr_diff, changed_files)` → Returns categorized issues

**Example Output:**
```json
{
  "issues": [...],
  "logic_issues": ["null pointer risk", "off-by-one error"],
  "security_issues": ["shell injection vulnerability"],
  "style_issues": ["naming convention violation"],
  "summary": "4 issues found: 2 logic, 1 security, 1 style"
}
```

#### TestAgent (`src/agents/test.py`)
**Responsibility:** Autonomous test generation
- Analyzes changed code for test coverage gaps
- Generates pytest test cases automatically
- Covers edge cases, boundaries, and error conditions

**Key Methods:**
- `generate_test_cases(pr_diff, changed_files)` → Returns list of test cases

**Example Output:**
```json
{
  "test_cases": [
    {
      "function": "calculate_average",
      "tests": ["test_empty_list", "test_single_item", "test_normal_case"],
      "code": "def test_calculate_average_empty_list(): ..."
    }
  ]
}
```

#### WriterAgent (`src/agents/writer.py`)
**Responsibility:** Bug detection and automated fixing
- Extracts buggy files from PR diffs
- Generates fixes using Gemini with explicit bug descriptions
- **Self-healing**: Tests fixes automatically before committing
- Reverts on test failure; commits on test success

**Key Methods:**
- `analyze_and_fix(pr_diff, repo_path)` → Returns list of fixes
- `apply_fix_and_verify(file_path, new_code)` → Applies fix and runs tests

**Self-Healing Process:**
1. Backup original file
2. Apply fix to file
3. Run pytest on modified file
4. If tests pass: keep fix and return success
5. If tests fail: revert file and return error

**JSON Parsing Enhancement:**
WriterAgent includes a sophisticated JSON parser that handles Gemini's actual newline characters in string values:
- Character-by-character scanning to escape newlines
- Converts actual `\n` characters to escaped `\\n`
- Parses with `json.loads()` without errors
- Decodes back to actual newlines in generated code

## Technical Details

### AI Model Integration

**Model:** Google Gemini 2.0 Flash
- Fast, accurate code analysis
- JSON mode for structured output
- Temperature: 0.1 (low randomness for consistency)

**Response Format:** JSON with MIME type `application/json`

**Example WriterAgent Prompt Structure:**
```
You are a Python Code Repair Agent. Fix these bugs:
1. calc.py: Add empty list check at START of calculate_average
2. list_processor.py: Fix range boundaries  
3. shell_executor.py: Add shlex.quote() sanitization

Return ONLY valid JSON Array with complete fixed files.
Use \n for newlines (not actual line breaks).
```

### GitHub API Integration

**GitHubAPIWrapper** (`src/utils/github_helper.py`)
- Authenticates using personal access tokens
- Fetches PR details, diffs, and changed files
- Handles API rate limiting
- Supports both public and private repositories

**Key Methods:**
- `get_pr_diff(owner, repo, pr_number)` → Raw diff
- `get_pr_details(owner, repo, pr_number)` → PR metadata
- `get_changed_files(owner, repo, pr_number)` → List of changed files

### Logging System

Uses **structlog** for structured, contextual logging:
- Agent-level logging with class names
- Contextual information (file names, counts, errors)
- JSON-formatted output for automation
- Separate log files in `logs/` directory

**Example Log Output:**
```json
{
  "event": "Successfully parsed JSON with 3 fixes",
  "level": "info",
  "timestamp": "2025-01-15T10:30:45.123Z"
}
```

## Requirements

### Core Dependencies
| Package | Version | Purpose |
|---------|---------|---------|
| `google-generativeai` | 0.3.0 | Gemini API integration |
| `PyGithub` | 2.4.0 | GitHub API client |
| `structlog` | 24.4.0 | Structured logging |
| `python-dotenv` | 1.0.1 | Environment configuration |

### Code Quality Tools
- `pytest` (8.3.2) - Test execution
- `bandit` (1.7.9) - Security scanning
- `pylint` (3.2.0) - Code linting
- `black` (24.8.0) - Code formatting
- `radon` (6.0.1) - Code metrics

### Optional
- `neo4j` (5.15.0) - Memory system (currently extensible, not required)
- `langchain` (0.3.0) - Prompt engineering utilities

## Error Handling

CodeCraft AI includes comprehensive error handling:

### JSON Parsing
- Automatic detection of markdown-wrapped JSON
- Character-by-character escaping of actual newlines
- Graceful fallback to text extraction

### File Operations
- Automatic backup before modifications
- Safe rollback on test failure
- Permission error detection and logging

### API Errors
- GitHub rate limit handling
- Gemini API timeout management
- Token validation at startup

## Extensibility

### Adding New Agents
1. Create new class in `src/agents/`
2. Inherit from base agent pattern (ReviewAgent as template)
3. Implement `analyze()` method
4. Register in `main.py` orchestrator

### Custom Prompts
Use `--custom-prompt` flag with analyze command:
```bash
python -m src.main analyze \
  --owner <user> \
  --repo <repo> \
  --pr-number <number> \
  --custom-prompt "Focus on performance optimizations"
```

### Memory Integration
Neo4j memory system is configured for future enhancements:
- Store agent analysis history
- Learn from previous fixes
- Build knowledge graphs of code patterns

## Examples

### Complete Workflow: Finding and Fixing Bugs
```bash
# 1. Review the PR for issues
python -m src.main review \
  --owner 0xIta3hi \
  --repo codecraft-test \
  --pr-number 2

# 2. Generate tests
python -m src.main test \
  --owner 0xIta3hi \
  --repo codecraft-test \
  --pr-number 2

# 3. Automatically fix bugs
python -m src.main fix \
  --owner 0xIta3hi \
  --repo codecraft-test \
  --pr-number 2 \
  --repo-path ../codecraft-test/
```

### Running Individual Agents
```bash
# Just fix bugs without review/test generation
python -m src.main fix \
  --owner myuser \
  --repo myrepo \
  --pr-number 15 \
  --repo-path ./my-local-repo/
```

## Troubleshooting

### Common Issues

**"GitHub token not provided"**
- Ensure `.env` file has `GITHUB_TOKEN`
- Token must have `repo` and `read:user` scopes

**"Gemini API key invalid"**
- Verify `GEMINI_API_KEY` in `.env`
- Check quota limits at [Google AI Studio](https://makersuite.google.com/app/apikey)

**"JSON parsing error: Expecting ',' delimiter"**
- Usually means actual newlines in JSON strings
- WriterAgent includes automatic character-by-character escaping
- Check logs for raw Gemini response

**"File does not exist" when fixing**
- Ensure `--repo-path` points to the actual repository directory
- Use absolute paths or paths relative to current working directory
- Example: `--repo-path /home/user/projects/my-repo/`

**Tests fail after fix applied**
- WriterAgent automatically reverts on test failure
- Check test error logs in `logs/` directory
- May indicate Gemini's fix was incomplete
- Try iterative refinement or different model

## Performance

- **Review Analysis:** ~2-5 seconds per PR
- **Test Generation:** ~3-7 seconds per file changed
- **Bug Fixing:** ~5-10 seconds per file (includes test verification)
- **API Calls:** Typically 3-5 Gemini API calls per complete analysis

## Future Roadmap

- [ ] DeepSeek model integration for alternative AI backend
- [ ] Iterative fix refinement (feed test failures back to AI)
- [ ] Neo4j memory system activation for learning
- [ ] Performance optimization caching
- [ ] GitHub Actions integration
- [ ] Support for multiple languages (Java, Go, TypeScript)
- [ ] Custom rule definitions for organization-specific checks

## Contributing

Contributions are welcome! Areas for improvement:
- Prompt engineering for better AI fixes
- Additional agent types (SecurityAgent, PerformanceAgent)
- Database-backed memory system
- Caching for repeated analysis
- Support for other version control systems

## License

MIT License - See LICENSE file for details

## Contact & Support

- **Author:** 0xIta3hi
- **Issues:** [GitHub Issues](https://github.com/0xIta3hi/codecraft-ai/issues)
- **Discussions:** [GitHub Discussions](https://github.com/0xIta3hi/codecraft-ai/discussions)

---

**Made with ❤️ for better code quality automation**
