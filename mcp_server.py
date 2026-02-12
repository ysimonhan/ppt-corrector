#!/usr/bin/env python3
"""
MCP Server for PowerPoint Correction Tools

Exposes two tools via MCP Streamable HTTP transport:
  - correct_pptx            : Fix spelling/grammar, return corrected base64 file + report
  - correct_pptx_highlighted : Same, with changed words highlighted in yellow

Run locally:
    python mcp_server.py                       # default port 8000
    MCP_PORT=3000 python mcp_server.py         # custom port

Environment variables:
    LANGDOCK_API_KEY  – Required. Key for the Langdock Completion API (LLM calls).
    MCP_API_KEY       – Optional. Protects the MCP server with Bearer auth.
                        If not set, auth is disabled (for local development).
    MCP_PORT          – Optional. Server port (default: 8000).
"""

import asyncio
import base64
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

# Ensure sibling modules (ppt_corrector, ppt_corrector_highlighted) are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── MCP Server ────────────────────────────────────────────────

mcp = FastMCP(
    "ppt-corrector",
    instructions=(
        "PowerPoint spelling & grammar correction tools. "
        "Send a base64-encoded .pptx file and get the corrected version back."
    ),
)


# ── API-key auth middleware ───────────────────────────────────

_MCP_API_KEY = os.getenv("MCP_API_KEY", "").strip()

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
                    ErrorData(
                        code=-32000,
                        message="Unauthorized: invalid or missing API key",
                    )
                )

            return await call_next(context)

    mcp.add_middleware(_ApiKeyAuth())
    logger.info("API-key auth enabled for MCP server")
else:
    logger.warning(
        "MCP_API_KEY not set — server is unprotected (OK for local dev)"
    )


# ── Tools ─────────────────────────────────────────────────────


@mcp.tool()
async def correct_pptx(
    file_base64: str, filename: str = "presentation.pptx"
) -> str:
    """Correct spelling and grammar errors in a PowerPoint presentation.

    Accepts a base64-encoded .pptx file, corrects all spelling and grammar
    errors using Claude Sonnet 4.5 via Langdock, and returns the corrected
    file plus a change report.

    Args:
        file_base64: The .pptx file content encoded as a base64 string.
        filename: Original filename (used for naming the output file).

    Returns:
        JSON string containing:
          corrected_file_base64 – base64-encoded corrected .pptx
          filename              – output filename
          corrections_made      – number of corrections
          total_slides          – number of slides processed
          changes               – list of {slide, shape, original, corrected}
    """
    return await asyncio.get_running_loop().run_in_executor(
        None, _correct_sync, file_base64, filename, False, "FFFF00"
    )


@mcp.tool()
async def correct_pptx_highlighted(
    file_base64: str,
    filename: str = "presentation.pptx",
    highlight_color: str = "FFFF00",
) -> str:
    """Correct spelling/grammar and highlight every change with a colored marker.

    Same as correct_pptx, but every corrected word is highlighted with a
    colored marker (default: yellow) so reviewers can spot what changed.

    Args:
        file_base64: The .pptx file content encoded as a base64 string.
        filename: Original filename (used for naming the output file).
        highlight_color: Hex RGB color for the highlight marker
                         (default FFFF00 = yellow).

    Returns:
        JSON string containing:
          corrected_file_base64 – base64-encoded corrected .pptx
          filename              – output filename
          corrections_made      – number of corrections
          total_slides          – number of slides processed
          highlight_color       – the hex color used
          changes               – list of {slide, shape, original, corrected}
    """
    return await asyncio.get_running_loop().run_in_executor(
        None, _correct_sync, file_base64, filename, True, highlight_color
    )


# ── Sync helper (runs in thread-pool) ────────────────────────


def _correct_sync(
    file_base64: str, filename: str, highlighted: bool, color: str
) -> str:
    """Run the synchronous PPT correction logic in a worker thread."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / filename
        stem = Path(filename).stem
        output_path = Path(tmpdir) / f"{stem}_v_correctedbyai.pptx"

        # Decode & write input file
        input_path.write_bytes(base64.b64decode(file_base64))

        # Call the appropriate corrector
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

        # Read & encode corrected file
        corrected_b64 = base64.b64encode(output_path.read_bytes()).decode(
            "utf-8"
        )

        response: dict = {
            "corrected_file_base64": corrected_b64,
            "filename": f"{stem}_v_correctedbyai.pptx",
            "corrections_made": result["corrections_made"],
            "total_slides": result["total_slides"],
            "changes": result["changes"],
        }
        if highlighted:
            response["highlight_color"] = f"#{color.lstrip('#')}"

        return json.dumps(response, ensure_ascii=False)


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8000"))
    logger.info("Starting PPT Corrector MCP server on 0.0.0.0:%d", port)
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        stateless_http=True,
    )
