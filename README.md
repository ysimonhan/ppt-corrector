# PowerPoint Spelling & Grammar Corrector

An AI-powered FastAPI service that corrects spelling and grammar in PowerPoint files using **Claude Sonnet 4.5** via the **Langdock API**. Consultants upload a `.pptx` to Langdock, Langdock’s sandbox sends it to the backend, and the backend returns a corrected file as a base64 payload.

The service preserves formatting at the run level and supports an optional highlighted output mode for reviewed changes. It is designed for Railway deployment in the EU region with in-memory job processing and no file writes during correction.

## Architecture

```text
Langdock custom action
  |
  | POST /jobs?highlight=false
  | Body: { file_base64, file_name }
  v
FastAPI backend on Railway
  |
  | Background job
  | - decode base64 into BytesIO
  | - extract text from slides
  | - call Langdock LLM API
  | - preserve formatting and optionally highlight changes
  | - store status in jobs dict
  v
GET /jobs/{job_id}
  |
  | { status: processing | done | error, metadata }
  v
GET /jobs/{job_id}/file
  |
  | { file_base64, file_name, mime_type }
  v
Langdock action returns corrected PPTX file
```

## API

`GET /health`

```json
{ "status": "ok" }
```

`POST /jobs?highlight=false`

Headers:

```text
Authorization: Bearer <API_KEY>
```

Body:

```json
{
  "file_base64": "...",
  "file_name": "presentation.pptx"
}
```

Response:

```json
{ "job_id": "<uuid>" }
```

`GET /jobs/{job_id}`

Headers:

```text
Authorization: Bearer <API_KEY>
```

Responses:

```json
{ "status": "processing" }
```

```json
{
  "status": "done",
  "file_name": "presentation_corrected.pptx",
  "corrections_count": 12,
  "changes": [
    { "slide": 1, "original": "Teh strategc obiectives for Q3", "corrected": "The strategic objectives for Q3" }
  ]
}
```

```json
{ "status": "error", "message": "..." }
```

`GET /jobs/{job_id}/file`

Headers:

```text
Authorization: Bearer <API_KEY>
```

Response:

```json
{
  "file_base64": "...",
  "file_name": "presentation_corrected.pptx",
  "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
}
```

## Local Development

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `API_KEY` | Yes | Bearer token required on `/jobs` endpoints |
| `LANGDOCK_API_KEY` | Yes | Langdock API key for Claude calls |
| `LANGDOCK_API_URL` | Yes | Langdock completions endpoint |
| `PORT` | Yes in Railway | Port for FastAPI / Uvicorn |

Optional:

| Variable | Purpose |
| --- | --- |
| `LANGDOCK_MODEL` | Override the Claude model if needed |

## Langdock Integration Setup

1. Create a custom integration in Langdock.
2. Add a file input named `document`.
3. Add a boolean input named `highlight`, defaulting to `false`.
4. Add an API key auth field that stores the backend bearer token.
5. Paste the reference action from [`langdock/action_correct_pptx.js`](./langdock/action_correct_pptx.js).
6. Configure the action to call the Railway service URL for `POST /jobs`, `GET /jobs/{job_id}`, and `GET /jobs/{job_id}/file`.
7. Set the auth field slug to `apiKey`, or update the script to use your chosen `data.auth.<slug>` value.

Important: Langdock documents a **2-minute execution timeout** for custom actions. The reference script polls in the sandbox, but it must still fit inside that timeout budget. If a job is still processing when the sandbox limit is reached, the action should return a clear in-progress error and let the user retry.

## Railway Deployment

1. Create a Railway service from this repository.
2. Use the root `Dockerfile`.
3. Set the Railway region to **EU West Metal, Amsterdam** in the Railway dashboard.
4. Add the runtime variables `API_KEY`, `LANGDOCK_API_KEY`, `LANGDOCK_API_URL`, and `PORT`.
5. Configure the health check path as `/health`.

## Tests

```bash
venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

## Notes

- Processing is fully in memory.
- No files are written to disk during correction.
- The FastAPI job store is ephemeral; a restart clears pending jobs.
- The backend keeps the original McKinsey-style correction prompt and run-level formatting preservation logic.
