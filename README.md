# PowerPoint Spelling & Grammar Corrector

An AI-powered FastAPI service that corrects spelling and grammar in PowerPoint files through the Langdock API while preserving PowerPoint formatting at the run level. This branch moves the service toward a production-grade deployment model with durable job metadata, queued background processing, short-lived object storage, and audit events.

The correction logic itself stays the same: the McKinsey-style system prompt, retry behavior, run-level formatting preservation, and optional XML highlighting are preserved. What changes here is the operational wrapper around that logic.

## Architecture

```text
Langdock custom action
  |
  | POST /jobs?highlight=false
  | Body: { file_base64, file_name }
  v
FastAPI API service
  |
  | validate auth + payload
  | store input PPTX in object storage
  | insert job row + audit event in Postgres
  | enqueue job in Redis or inline queue
  v
Worker
  |
  | load PPTX from object storage
  | call Langdock LLM API
  | preserve formatting / optionally highlight changes
  | store corrected PPTX in object storage
  | update job row + audit events
  v
GET /jobs/{job_id}
  |
  | read durable job state from Postgres
  | fetch output PPTX from object storage when done
  v
Langdock action returns corrected PPTX file
```

## Components

- API service: [app/main.py](./app/main.py)
- Worker task orchestration: [app/worker_tasks.py](./app/worker_tasks.py)
- Durable entities: [app/entities.py](./app/entities.py)
- Runtime assembly: [app/runtime.py](./app/runtime.py)
- Queue backends: [app/queueing.py](./app/queueing.py)
- Storage backends: [app/storage.py](./app/storage.py)
- Worker entrypoint: [app/worker.py](./app/worker.py)

## API

`GET /health`

```json
{ "status": "ok" }
```

`GET /auth/validate`

Headers:

```text
Authorization: Bearer <API_KEY>
```

Response:

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

### Minimal local mode

This mode keeps everything local and uses inline background execution plus in-memory object storage.

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Recommended local env values for minimal mode:

```env
QUEUE_BACKEND=inline
STORAGE_BACKEND=memory
DATABASE_URL=sqlite:///./ppt_corrector.db
```

### Queue-backed local mode

This mode is closer to production and runs the API and worker separately.

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.worker
```

Use this with:

```env
QUEUE_BACKEND=redis
STORAGE_BACKEND=s3
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://localhost:6379/0
```

## Environment Variables

Required:

| Variable | Purpose |
| --- | --- |
| `API_KEY` | Bearer token for `/auth/validate` and `/jobs` |
| `LANGDOCK_API_KEY` | Langdock API key for LLM calls |

Core runtime:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LANGDOCK_API_URL` | `https://api.langdock.com/anthropic/eu/v1/messages` | Langdock endpoint |
| `LANGDOCK_MODEL` | `claude-sonnet-4-6` | Model name passed to Langdock |
| `PORT` | `8000` | API port |
| `MIN_TEXT_LENGTH` | `3` | Skip trivial text nodes |
| `LLM_TIMEOUT_SECONDS` | `60` | HTTP timeout for Langdock requests |
| `MAX_UPLOAD_SIZE_BYTES` | `52428800` | Upload size limit |
| `DEFAULT_HIGHLIGHT_COLOR` | `FFFF00` | PPT highlight color |

Durability and retention:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./ppt_corrector.db` | Job and audit metadata database |
| `JOB_TTL_SECONDS` | `3600` | How long file content stays retrievable |
| `JOB_CLEANUP_INTERVAL_SECONDS` | `60` | Cleanup loop frequency |
| `METADATA_RETENTION_SECONDS` | `604800` | How long job metadata and audit records are kept |

Queue configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `QUEUE_BACKEND` | `inline` | `inline` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for queued jobs |
| `RQ_QUEUE_NAME` | `ppt-corrector` | Queue name used by RQ |

Object storage configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `STORAGE_BACKEND` | `memory` | `memory` or `s3` |
| `S3_BUCKET` | empty | Bucket for input/output PPTX files |
| `S3_REGION` | `eu-central-1` | Bucket region |
| `S3_ENDPOINT_URL` | empty | Optional custom S3 endpoint |
| `S3_ACCESS_KEY_ID` | empty | S3 credential |
| `S3_SECRET_ACCESS_KEY` | empty | S3 credential |
| `S3_PREFIX` | `ppt-corrector` | Object key prefix |

## Audit Model

The branch introduces append-only audit events in Postgres. Each job writes events such as:

- `job_created`
- `job_processing_started`
- `job_completed`
- `job_failed`
- `job_content_deleted`

The intent is to keep metadata for support and compliance without logging slide text or full PPTX payloads.

## Langdock Integration Setup

1. Create a custom integration in Langdock.
2. Add a file input named `document`.
3. Add a boolean input named `highlight`, defaulting to `false`.
4. Add an auth field for the backend bearer token.
5. Use [langdock/action_correct_pptx.js](./langdock/action_correct_pptx.js) as the reference action.
6. Point the action to the API service URL for `POST /jobs` and `GET /jobs/{job_id}`.
7. Use the auth field slug expected by the action script.

Important: Langdock custom actions have a short runtime budget. The action should poll long enough for normal jobs, but still fail cleanly if the sandbox timeout is reached.

## Railway Deployment

For the production architecture, use separate Railway services that share the same image:

1. API service
2. Worker service
3. Postgres
4. Redis
5. Object storage provider compatible with S3

Recommended commands:

- API: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Worker: `python -m app.worker`

Recommended production settings:

- `QUEUE_BACKEND=redis`
- `STORAGE_BACKEND=s3`
- `DATABASE_URL=<Railway Postgres URL>`
- `REDIS_URL=<Railway Redis URL>`

The API service can keep using [railway.toml](./railway.toml) for its health check. The worker service should use the same image with an overridden start command.

## Tests

```bash
venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

## Current Status

- The durable architecture runs locally with `inline` queue plus `memory` storage.
- The queue-backed path is wired for `redis` plus `s3`, but this branch does not yet include migrations, worker supervision, or production monitoring.
- Correction logic, highlighting behavior, and the preserved system prompt are unchanged.
