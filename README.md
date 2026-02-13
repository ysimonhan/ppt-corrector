# PowerPoint Spelling & Grammar Corrector

An AI-powered tool that reads PowerPoint presentations, corrects spelling and grammar using **Claude Sonnet 4.5** via the [Langdock API](https://docs.langdock.com/api-endpoints/completion/anthropic), and saves a `_v_correctedbyai` version. Available as CLI scripts and as an MCP server for Langdock agents.

## Features

- **LLM-powered correction** -- Uses Claude Sonnet 4.5 for high-quality corrections
- **Full text extraction** -- Handles text frames, tables, and grouped shapes
- **Preserves formatting** -- Only text content is corrected; layout and styling stay intact
- **Highlighted mode** -- Optionally highlights changed words with a yellow marker
- **Correction report** -- Optional JSON report of all changes made
- **MCP Server** -- Expose both tools to Langdock agents (or any MCP client) over HTTP
- **Secure file transfer** -- Files uploaded via custom integration, one-time download links
- **Retries** -- Auto-retry with exponential backoff for transient API errors

---

## Architecture (Langdock Agent)

The system uses a two-step approach for secure file handling:

```
User uploads .pptx in Langdock chat
        |
        v
[Custom Integration: upload_pptx]  -->  POST /api/upload  -->  returns file_id
        |
        v
[MCP Tool: correct_pptx(file_id)]  -->  Processes file via LLM  -->  returns download_url
        |
        v
User clicks download link (one-time, file deleted after download)
```

**Why two steps:**

- **Custom integration** (upload): handles binary files natively via Langdock's `FileData`, stays within 2-min timeout
- **MCP tool** (processing): can run for minutes (SSE streaming), handles LLM calls per slide

## MCP Server (for Langdock agents)

### Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/upload` | POST | Bearer token | Upload .pptx (JSON with base64), returns `file_id` |
| `/mcp` | POST | Bearer token | MCP Streamable HTTP (tools below) |
| `/files/{id}` | GET | None (UUID) | One-time download of corrected .pptx |

### MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `correct_pptx` | `file_id` | Correct spelling/grammar, return download URL |
| `correct_pptx_highlighted` | `file_id`, `highlight_color` | Same, with changed words highlighted |

### Deployed instance

- **MCP endpoint**: `https://ppt-corrector-production.up.railway.app/mcp`
- **Upload endpoint**: `https://ppt-corrector-production.up.railway.app/api/upload`

---

## Setup: Langdock Agent

### 1. Connect MCP tools

1. In Langdock, go to an agent's settings or the MCP integration page
2. Enter the MCP server URL: `https://ppt-corrector-production.up.railway.app/mcp`
3. Select **API Key** authentication
4. Enter the `MCP_API_KEY` value
5. Click **Test connection** -- both tools will be auto-discovered
6. Select the tools and save

### 2. Create the custom integration

Create a new custom integration in Langdock called **"PPT Corrector"** with one action:

**Action: `upload_pptx`**

- **Input field**: `file` (type: FILE, required)
- **Authentication**: API Key (value = your `MCP_API_KEY`)
- **Code** (runs in Langdock's JS sandbox):

```javascript
const file = data.input.file;
const response = await ld.request({
  method: "POST",
  url: "https://ppt-corrector-production.up.railway.app/api/upload",
  headers: {
    "Authorization": `Bearer ${data.auth.apiKey}`,
    "Content-Type": "application/json"
  },
  body: {
    filename: file.fileName,
    base64: file.base64,
    mimeType: file.mimeType
  }
});
return {
  file_id: response.json.file_id,
  filename: response.json.filename,
  message: `File uploaded. Use file_id "${response.json.file_id}" to correct it.`
};
```

### 3. Assign to agent

Add both the MCP tools and the custom integration to your Langdock agent. The agent will:

1. Accept the user's uploaded .pptx
2. Call `upload_pptx` (custom integration) to get a `file_id`
3. Call `correct_pptx(file_id)` or `correct_pptx_highlighted(file_id)` (MCP tool)
4. Return the one-time download link to the user

---

## Security

| Measure | Details |
|---------|---------|
| **Auth on upload** | `POST /api/upload` requires `Authorization: Bearer {MCP_API_KEY}` |
| **Auth on MCP** | MCP middleware checks Bearer token |
| **One-time download** | Corrected file deleted from disk after first `GET /files/{id}` |
| **Unguessable URLs** | File IDs are UUID4 -- no auth needed for download link |
| **15-min auto-purge** | Background task deletes any files older than 15 min |
| **No persistent storage** | All files in `/tmp`, wiped on container restart |
| **No sensitive logs** | Server only logs file_id, slide count, correction count -- never slide text |
| **File validation** | .pptx only (ZIP magic bytes + extension), max 50 MB |
| **HTTPS only** | Enforced by Railway |

---

## Run locally

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
| `MCP_API_KEY` | No | Protects upload + MCP endpoints (Bearer token) |
| `PUBLIC_URL` | Production | Base URL for download links (e.g. Railway URL) |
| `MCP_PORT` / `PORT` | No | Server port (default: 8000) |

## Requirements

- Python 3.10+
- Langdock API key
- `.pptx` files (PowerPoint 2007+)
