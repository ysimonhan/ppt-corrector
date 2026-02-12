# PowerPoint Spelling & Grammar Corrector

An AI-powered tool that reads PowerPoint presentations, corrects spelling and grammar using **Claude Sonnet 4.5** via the [Langdock API](https://docs.langdock.com/api-endpoints/completion/anthropic), and saves a `_v_correctedbyai` version. Available as CLI scripts and as an MCP server for Langdock agents.

## Features

- **LLM-powered correction** -- Uses Claude Sonnet 4.5 for high-quality corrections
- **Full text extraction** -- Handles text frames, tables, and grouped shapes
- **Preserves formatting** -- Only text content is corrected; layout and styling stay intact
- **Highlighted mode** -- Optionally highlights changed words with a yellow marker
- **Correction report** -- Optional JSON report of all changes made
- **MCP Server** -- Expose both tools to Langdock agents (or any MCP client) over HTTP
- **Retries** -- Auto-retry with exponential backoff for transient API errors

---

## MCP Server (for Langdock agents)

The MCP server exposes two tools that any MCP-compatible client can call:

| Tool | Description |
|------|-------------|
| `correct_pptx` | Correct spelling/grammar, return corrected file |
| `correct_pptx_highlighted` | Same, with changed words highlighted in yellow |

### Deployed instance

The server is deployed on Railway:

- **MCP endpoint**: `https://ppt-corrector-production.up.railway.app/mcp`
- **Auth**: API Key (Bearer token)

### Connect to Langdock

1. In Langdock, go to an agent's settings or the MCP integration page
2. Enter the MCP server URL: `https://ppt-corrector-production.up.railway.app/mcp`
3. Select **API Key** authentication
4. Enter the MCP API key
5. Click **Test connection** -- both tools will be auto-discovered
6. Select the tools and save

### Run locally

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python mcp_server.py           # starts on http://localhost:8000/mcp
```

Set `MCP_API_KEY` in `.env` to enable auth, or leave unset for local dev.

---

## CLI Usage

### Setup

1. **Create a virtual environment** (recommended):

   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   # or: source venv/bin/activate   # macOS/Linux
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Langdock API key**:

   - Copy `.env.example` to `.env`
   - Add your Langdock API key (get one at [app.langdock.com](https://app.langdock.com)):

   ```env
   LANGDOCK_API_KEY=your_api_key_here
   ```

### Correct without highlighting

```bash
python ppt_corrector.py MyPresentation.pptx
python ppt_corrector.py MyPresentation.pptx -o CorrectedVersion.pptx
python ppt_corrector.py MyPresentation.pptx --no-report
```

### Correct with highlighted changes

```bash
python ppt_corrector_highlighted.py MyPresentation.pptx
python ppt_corrector_highlighted.py MyPresentation.pptx --color FF9632  # orange
```

## Output

- **Corrected file**: `{original_name}_v_correctedbyai.pptx` in the same folder as the input
- **Report** (optional): `{corrected_name}_report.json` with a list of all changes

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LANGDOCK_API_KEY` | Yes | Langdock API key for LLM calls |
| `MCP_API_KEY` | No | Protects MCP server (clients send `Authorization: Bearer <key>`) |
| `MCP_PORT` / `PORT` | No | Server port (default: 8000) |

## Requirements

- Python 3.10+
- Langdock API key
- `.pptx` files (PowerPoint 2007+)
