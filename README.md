# PowerPoint Spelling & Grammar Corrector

An AI-powered FastAPI service that corrects spelling and grammar in PowerPoint files using **Claude Sonnet 4.5** via the **Langdock API**. Consultants upload a `.pptx` to Langdock, Langdock starts a background correction job, and a follow-up action retrieves the corrected file as a base64 payload.

The service preserves formatting at the run level and supports an optional highlighted output mode for reviewed changes. It is designed for Railway deployment in the EU region with in-memory job processing and no file writes during correction.

## Architecture

```text
Langdock Action 1: Start Correction
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
  | - store result in jobs dict
  v
Langdock Action 2: Get Correction Result
  |
  | GET /jobs/{job_id}
  | { status: processing | done | error }
  v
Langdock action returns corrected PPTX file in chat
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
  "file_base64": "...",
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
| `JOB_TTL_SECONDS` | How long jobs stay available in memory. Default: `3600` |
| `JOB_CLEANUP_INTERVAL_SECONDS` | How often expired jobs are purged. Default: `60` |

## Langdock Integration Setup

1. Create a custom integration in Langdock.
2. Add an API key auth field that stores the backend bearer token.
3. Create **Action 1: Start Correction**.
4. Add a file input named `document`.
5. Add a boolean input named `highlight`, defaulting to `false`.
6. Paste the reference action from [`langdock/action_start_correction.js`](./langdock/action_start_correction.js).
7. Set the auth field slug to `apiKey`, or update the script to use your chosen `data.auth.<slug>` value.
8. Create **Action 2: Get Correction Result**.
9. Add a text input named `jobId`.
10. Paste the reference action from [`langdock/action_get_correction_result.js`](./langdock/action_get_correction_result.js).

Important: Langdock documents a **2-minute execution timeout** for custom actions. The two-action setup avoids long polling in one action: the first action only creates the job, and the second action retrieves the result later with the `job_id`.

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
- The FastAPI job store is ephemeral; a restart clears pending jobs and completed results that were not yet retrieved.
- The backend keeps the original McKinsey-style correction prompt and run-level formatting preservation logic.
