#!/usr/bin/env python3
"""
MCP Server for PowerPoint Correction Tools

Architecture:
  1. Langdock custom integration uploads .pptx via POST /api/upload -> gets file_id
  2. Langdock agent calls MCP tool correct_pptx(file_id) -> gets download_url
  3. User clicks download_url (one-time link, file deleted after download)

Endpoints:
  POST /api/upload           – Upload .pptx (JSON with base64), returns file_id
  GET  /files/{file_id}      – One-time download of corrected .pptx
  POST /mcp                  – MCP Streamable HTTP (tools: correct_pptx, correct_pptx_highlighted)

Environment variables:
  LANGDOCK_API_KEY  – Required. Key for the Langdock Completion API (LLM calls).
  MCP_API_KEY       – Optional. Protects upload + MCP endpoints with Bearer auth.
  PUBLIC_URL        – Required in production. Base URL for download links.
  PORT / MCP_PORT   – Optional. Server port (default: 8000).
"""

import asyncio
import base64
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

# Ensure sibling modules are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────

_MCP_API_KEY = os.getenv("MCP_API_KEY", "").strip()
_PUBLIC_URL = os.getenv(
    "PUBLIC_URL",
    f"http://localhost:{os.getenv('PORT', os.getenv('MCP_PORT', '8000'))}",
).rstrip("/")

_TMP_BASE = Path(tempfile.gettempdir())
_UPLOAD_DIR = _TMP_BASE / "ppt-uploads"
_RESULT_DIR = _TMP_BASE / "ppt-results"
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
_FILE_TTL_SECONDS = 15 * 60  # 15 minutes

# Ensure directories exist
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_RESULT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory registry: file_id -> {path, filename, created_at}
_uploads: dict = {}
_results: dict = {}


# ── Helpers ───────────────────────────────────────────────────


def _check_bearer(request: Request) -> bool:
    """Return True if the request carries a valid Bearer token (or auth is disabled)."""
    if not _MCP_API_KEY:
        return True
    auth = request.headers.get("authorization", "")
    return auth == f"Bearer {_MCP_API_KEY}"


def _validate_pptx_bytes(data: bytes, filename: str) -> None:
    """Raise ValueError if data isn't a valid .pptx."""
    if len(data) < 100:
        raise ValueError(f"File is only {len(data)} bytes – likely empty or corrupt.")
    if data[:4] != b"PK\x03\x04":
        raise ValueError("File is not a valid .pptx (ZIP) package.")
    if not filename.lower().endswith((".pptx", ".ppt")):
        raise ValueError(f"Unsupported extension: {filename}. Only .pptx is accepted.")


def _purge_expired(registry: dict, base_dir: Path) -> int:
    """Delete expired entries from a registry and disk. Returns count deleted."""
    now = time.time()
    expired = [fid for fid, meta in registry.items() if now - meta["created_at"] > _FILE_TTL_SECONDS]
    for fid in expired:
        meta = registry.pop(fid, None)
        if meta:
            parent = meta["path"].parent
            if parent.exists():
                shutil.rmtree(parent, ignore_errors=True)
    return len(expired)


# ── MCP Server ────────────────────────────────────────────────

mcp = FastMCP(
    "ppt-corrector",
    instructions=(
        "PowerPoint spelling & grammar correction tools. "
        "The user uploads a .pptx via the upload_pptx integration, which returns a file_id. "
        "Then call correct_pptx(file_id) or correct_pptx_highlighted(file_id) to process it. "
        "The tool returns a one-time download URL for the corrected file."
    ),
)


# ── MCP auth middleware ───────────────────────────────────────

if _MCP_API_KEY:
    from fastmcp.server.middleware import Middleware, MiddlewareContext

    class _ApiKeyAuth(Middleware):
        """Reject MCP requests that lack a valid Bearer token."""

        async def on_request(self, context: MiddlewareContext, call_next):
            authorized = False
            try:
                from fastmcp.server.dependencies import get_http_headers

                headers = get_http_headers()
                if headers:
                    auth_header = headers.get("authorization", "")
                    authorized = auth_header == f"Bearer {_MCP_API_KEY}"
            except Exception:
                pass

            if not authorized:
                from mcp import McpError
                from mcp.types import ErrorData

                raise McpError(
                    ErrorData(code=-32000, message="Unauthorized: invalid or missing API key")
                )

            return await call_next(context)

    mcp.add_middleware(_ApiKeyAuth())
    logger.info("API-key auth enabled")
else:
    logger.warning("MCP_API_KEY not set — server is unprotected (OK for local dev)")


# ── Custom routes: upload + download ─────────────────────────


@mcp.custom_route("/api/upload", methods=["POST"])
async def upload_file(request: Request) -> JSONResponse:
    """Accept a .pptx file (JSON with base64) from the Langdock custom integration."""
    if not _check_bearer(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    filename = body.get("filename", "")
    b64_data = body.get("base64", "")
    if not filename or not b64_data:
        return JSONResponse(
            {"error": "Missing required fields: filename, base64"}, status_code=400
        )

    # Decode base64
    try:
        file_bytes = base64.b64decode(b64_data)
    except Exception:
        return JSONResponse({"error": "Invalid base64 data"}, status_code=400)

    # Size check
    if len(file_bytes) > _MAX_FILE_SIZE:
        return JSONResponse(
            {"error": f"File too large ({len(file_bytes)} bytes). Max: {_MAX_FILE_SIZE} bytes."},
            status_code=413,
        )

    # Validate .pptx
    safe_name = Path(filename).name or "presentation.pptx"
    try:
        _validate_pptx_bytes(file_bytes, safe_name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # Store
    file_id = str(uuid.uuid4())
    file_dir = _UPLOAD_DIR / file_id
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / safe_name
    file_path.write_bytes(file_bytes)

    _uploads[file_id] = {
        "path": file_path,
        "filename": safe_name,
        "created_at": time.time(),
    }

    logger.info("Upload: file_id=%s filename=%s size=%d bytes", file_id, safe_name, len(file_bytes))

    return JSONResponse({
        "file_id": file_id,
        "filename": safe_name,
        "size_bytes": len(file_bytes),
        "expires_in_minutes": _FILE_TTL_SECONDS // 60,
    })


@mcp.custom_route("/files/{file_id}", methods=["GET"])
async def download_result(request: Request) -> FileResponse | JSONResponse:
    """One-time download of a corrected .pptx. File is deleted after download."""
    file_id = request.path_params.get("file_id", "")

    meta = _results.get(file_id)
    if not meta or not meta["path"].exists():
        _results.pop(file_id, None)
        return JSONResponse({"error": "File not found or already downloaded"}, status_code=404)

    file_path = meta["path"]
    filename = meta["filename"]

    # Mark as consumed immediately (before streaming) to prevent double-download
    _results.pop(file_id, None)

    logger.info("Download: file_id=%s filename=%s (one-time)", file_id, filename)

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        background=_make_cleanup_task(file_path.parent),
    )


def _make_cleanup_task(directory: Path):
    """Return a Starlette BackgroundTask that deletes a directory after response."""
    from starlette.background import BackgroundTask

    def _delete():
        shutil.rmtree(directory, ignore_errors=True)

    return BackgroundTask(_delete)


# ── MCP Tools ─────────────────────────────────────────────────


@mcp.tool()
async def correct_pptx(file_id: str) -> str:
    """Correct spelling and grammar in a previously uploaded PowerPoint file.

    The user must first upload the .pptx via the upload_pptx integration,
    which returns a file_id. Pass that file_id here.

    Args:
        file_id: The UUID returned by the upload_pptx integration.

    Returns:
        JSON with download_url (one-time link), filename, corrections_made,
        total_slides, and a list of changes.
    """
    return await asyncio.get_running_loop().run_in_executor(
        None, _process_file, file_id, False, "FFFF00"
    )


@mcp.tool()
async def correct_pptx_highlighted(
    file_id: str,
    highlight_color: str = "FFFF00",
) -> str:
    """Correct spelling/grammar and highlight every change with a colored marker.

    Same as correct_pptx but changed words are highlighted (default: yellow).
    The user must first upload the .pptx via the upload_pptx integration.

    Args:
        file_id: The UUID returned by the upload_pptx integration.
        highlight_color: Hex RGB color for highlights (default FFFF00 = yellow).

    Returns:
        JSON with download_url (one-time link), filename, corrections_made,
        total_slides, highlight_color, and a list of changes.
    """
    return await asyncio.get_running_loop().run_in_executor(
        None, _process_file, file_id, True, highlight_color
    )


# ── Processing logic (runs in thread pool) ────────────────────


def _process_file(file_id: str, highlighted: bool, color: str) -> str:
    """Look up an uploaded file by ID, correct it, store the result, return JSON."""

    # Validate file_id format
    try:
        uuid.UUID(file_id)
    except ValueError:
        raise ValueError(f"Invalid file_id format: {file_id}")

    # Look up the upload
    meta = _uploads.get(file_id)
    if not meta or not meta["path"].exists():
        _uploads.pop(file_id, None)
        raise FileNotFoundError(
            f"No uploaded file found for file_id '{file_id}'. "
            "It may have expired (15 min) or already been processed. "
            "Please upload the file again using the upload_pptx integration."
        )

    input_path = meta["path"]
    safe_name = meta["filename"]
    stem = Path(safe_name).stem

    # Prepare result directory
    result_id = str(uuid.uuid4())
    result_dir = _RESULT_DIR / result_id
    result_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{stem}_v_correctedbyai.pptx"
    output_path = result_dir / output_name

    logger.info(
        "Processing: file_id=%s filename=%s highlighted=%s",
        file_id, safe_name, highlighted,
    )

    # Suppress corrector modules' verbose text logging (they log slide content
    # at INFO level, which we must avoid for data security in production).
    _corrector_logger_names = [
        "ppt_corrector",
        "ppt_corrector_highlighted",
    ]
    _saved_levels = {}
    for name in _corrector_logger_names:
        cl = logging.getLogger(name)
        _saved_levels[name] = cl.level
        cl.setLevel(logging.WARNING)

    try:
        # Run the appropriate corrector
        if highlighted:
            from ppt_corrector_highlighted import correct_powerpoint_highlighted

            result = correct_powerpoint_highlighted(
                str(input_path),
                output_file=str(output_path),
                save_report=False,
                highlight_color=color.lstrip("#"),
            )
        else:
            from ppt_corrector import correct_powerpoint

            result = correct_powerpoint(
                str(input_path),
                output_file=str(output_path),
                save_report=False,
            )
    finally:
        # Restore original log levels
        for name, level in _saved_levels.items():
            logging.getLogger(name).setLevel(level)

    # Delete the upload now that processing is done
    _uploads.pop(file_id, None)
    upload_dir = _UPLOAD_DIR / file_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    # Register the result for one-time download
    _results[result_id] = {
        "path": output_path,
        "filename": output_name,
        "created_at": time.time(),
    }

    download_url = f"{_PUBLIC_URL}/files/{result_id}"

    logger.info(
        "Done: file_id=%s corrections=%d slides=%d result_id=%s",
        file_id, result["corrections_made"], result["total_slides"], result_id,
    )

    # Build response — only metadata, no slide text
    response: dict = {
        "download_url": download_url,
        "filename": output_name,
        "corrections_made": result["corrections_made"],
        "total_slides": result["total_slides"],
        "changes": [
            {
                "slide": c["slide"],
                "original": c["original"],
                "corrected": c["corrected"],
            }
            for c in result.get("changes", [])
        ],
    }
    if highlighted:
        response["highlight_color"] = f"#{color.lstrip('#')}"

    return json.dumps(response, ensure_ascii=False)


# ── Background cleanup (daemon thread) ───────────────────────


def _cleanup_thread():
    """Periodically delete expired uploads and results (runs in background thread)."""
    while True:
        time.sleep(300)  # every 5 minutes
        try:
            u = _purge_expired(_uploads, _UPLOAD_DIR)
            r = _purge_expired(_results, _RESULT_DIR)
            if u or r:
                logger.info("Cleanup: purged %d uploads, %d results", u, r)
        except Exception as e:
            logger.error("Cleanup error: %s", e)


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("MCP_PORT", "8000")))
    logger.info("Starting PPT Corrector MCP server on 0.0.0.0:%d", port)
    logger.info("Public URL: %s", _PUBLIC_URL)

    # Start background cleanup thread (daemon = dies with main process)
    _cleaner = threading.Thread(target=_cleanup_thread, daemon=True)
    _cleaner.start()

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        stateless_http=True,
    )
