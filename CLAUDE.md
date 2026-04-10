# Claude Code Project Instructions

## Git Workflow
- Always commit and push directly to `main`. No feature branches, no PRs.
- Use `git push -u origin main` for pushes.

## Project Overview
Clanker is a self-hosted LLM-powered smart home assistant built on top of Home Assistant.
- Python 3.11+, fully async
- Uses: anthropic, openai, httpx, websockets, pydantic v2, aiosqlite, structlog, mcp
- Linting: ruff | Type checking: mypy --strict | Tests: pytest + pytest-asyncio
- Package manager: uv
