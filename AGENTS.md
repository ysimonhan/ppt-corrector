# Repository Guidelines

## Project Structure & Module Organization
- Core correction logic lives in `ppt_corrector.py` and `ppt_corrector_highlighted.py`.
- MCP/API entrypoint is `mcp_server.py` (routes: `/api/upload`, `/mcp`, `/files/{id}`).
- Basic test scripts are `test_api.py` and `test_e2e.py`.
- Utility/sample script: `create_sample.py`.
- Config files: `.env`, `.env.example`, `requirements.txt`, `Dockerfile`.
- Generated artifacts (sample PPTX outputs) should not be committed unless explicitly needed for debugging.

## Build, Test, and Development Commands
- Create environment (this repo uses `venv`):
  - `python -m venv venv`
  - `venv\Scripts\activate` (Windows)
- Install dependencies:
  - `pip install -r requirements.txt`
- Run MCP server locally:
  - `python mcp_server.py`
- Run correction scripts:
  - `python ppt_corrector.py <file.pptx>`
  - `python ppt_corrector_highlighted.py <file.pptx> --color FFFF00`
- Run tests:
  - `python test_api.py`
  - `python test_e2e.py`

## Coding Style & Naming Conventions
- Follow Python conventions: 4-space indentation, `snake_case` for functions/variables, `UPPER_SNAKE_CASE` for constants.
- Keep modules focused and avoid cross-file side effects.
- Prefer explicit validation and clear error messages for file, auth, and payload handling.
- Keep logging informative but never log secrets or full slide text.

## Testing Guidelines
- Add/update tests for behavior changes in upload, processing, and one-time download flows.
- Name new tests as `test_*.py`.
- For endpoint changes, cover both success and failure paths (auth, invalid payload, expired/missing `file_id`).

## Commit & Pull Request Guidelines
- Use concise, imperative commit subjects (pattern in history):
  - `Fix port binding: respect Railway PORT env var`
  - `Implement upload/download MCP workflow...`
- PRs should include:
  - What changed and why
  - Env/config changes (e.g., `PUBLIC_URL`, `MCP_API_KEY`)
  - How to test locally (exact commands)
  - Sample request/response for API changes when relevant

## Security & Configuration Tips
- Keep secrets in `.env`; never commit API keys.
- Validate uploaded files as `.pptx` (size, extension, ZIP magic bytes).
- Preserve one-time download semantics and cleanup behavior when editing file lifecycle code.
