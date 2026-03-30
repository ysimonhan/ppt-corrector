from __future__ import annotations

import logging
import threading
from typing import Any

import httpx
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential


logger = logging.getLogger(__name__)
_shared_http_client: httpx.Client | None = None
_shared_http_client_lock = threading.Lock()

SYSTEM_PROMPT = """You are a highly rated and experienced Engagement Manager from McKinsey & Company in Germany. You are super good at correcting spelling and grammar errors in texts.

<Task>
Your task is to correct ONLY spelling and grammar errors in the given text.
</Task>

<Context>
- You will often only get one word for correction. This is normal and expected since the data comes from a powerpoint presentation where the text needs to be extraced from each
object individually so often there is only one word. If there is no text, return an empty string. If you only get one word, return the corrected word.

Rules:
- Return ONLY the corrected text, nothing else. No explanations, no quotes, no preamble. 
- As context one word is enough. Do not ask questions or make assumptions, just correct the word.
- Preserve technical terms, proper nouns, brand names, and acronyms.
- Do not change formatting, punctuation style, or sentence structure unless grammatically wrong.
- If the text has no errors, return it unchanged.
- Keep the output the same length and style as the input.

"""


class InvalidApiKeyError(Exception):
    """Raised when the Langdock API rejects the configured key."""


class LangdockLLMClient:
    def __init__(
        self,
        api_key: str,
        api_url: str,
        model: str,
        min_text_length: int = 3,
        timeout_seconds: float = 60.0,
        http_client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "LANGDOCK_API_KEY not set. Add it to .env or export it. "
                "Get your key from https://app.langdock.com"
            )

        key = api_key.strip()
        if not key.startswith("sk-"):
            logger.warning("API key should usually start with 'sk-'. Check you copied the full key.")

        self.api_key = key
        self.api_url = api_url
        self.model = model
        self.min_text_length = min_text_length
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or _get_shared_http_client(timeout_seconds)

    def correct_text(self, text: str) -> tuple[str, bool]:
        text = text.strip()
        if len(text) < self.min_text_length:
            return text, True

        try:
            corrected = self._request_correction(text)
        except InvalidApiKeyError:
            logger.error(
                "401 Unauthorized: API key invalid. Check:\n"
                "  1. Key is correct in .env (Settings -> API in Langdock)\n"
                "  2. Key has scope for Completion/Anthropic API\n"
                "  3. Create a new key at https://app.langdock.com if needed"
            )
            return text, False
        except httpx.HTTPStatusError as exc:
            logger.error("LLM API error: %s - %s", exc.response.status_code, exc.response.text[:200])
            return text, False
        except Exception as exc:
            logger.error("LLM error for '%s...': %s", text[:30], exc)
            return text, False

        if not corrected:
            logger.warning("Empty response for: %s...", text[:50])
            return text, True

        return corrected, True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(InvalidApiKeyError),
        reraise=True,
    )
    def _request_correction(self, text: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": 512,
            "temperature": 0.2,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Correct spelling and grammar in this text. Return ONLY the corrected "
                        f"text:\n\n{text}"
                    ),
                }
            ],
        }

        response = self.http_client.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if response.status_code == 401:
            raise InvalidApiKeyError("Invalid Langdock API key")

        response.raise_for_status()
        data = response.json()

        corrected = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                corrected += block.get("text", "") or ""

        return corrected.strip()


def _build_http_client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout_seconds,
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
        ),
    )


def _get_shared_http_client(timeout_seconds: float) -> httpx.Client:
    global _shared_http_client

    if _shared_http_client is None:
        with _shared_http_client_lock:
            if _shared_http_client is None:
                _shared_http_client = _build_http_client(timeout_seconds)

    return _shared_http_client

