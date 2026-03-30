from __future__ import annotations

import httpx

from app.llm import InvalidApiKeyError, LangdockLLMClient, SYSTEM_PROMPT


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.com")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self) -> dict[str, object]:
        return self._payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, *args, **kwargs) -> FakeResponse:
        response = self.responses[self.calls]
        self.calls += 1
        return response


def test_system_prompt_is_preserved() -> None:
    assert "McKinsey & Company in Germany" in SYSTEM_PROMPT
    assert "correct ONLY spelling and grammar errors" in SYSTEM_PROMPT


def test_langdock_client_parses_successful_response(monkeypatch) -> None:
    fake_client = FakeClient(
        [FakeResponse(200, {"content": [{"type": "text", "text": "The strategic objectives"}]})]
    )

    client = LangdockLLMClient(
        api_key="sk-test",
        api_url="https://example.com",
        model="claude-sonnet-4-5-20250929",
        http_client=fake_client,
    )

    corrected, ok = client.correct_text("Teh strategc obiectives")

    assert ok is True
    assert corrected == "The strategic objectives"
    assert fake_client.calls == 1


def test_langdock_client_does_not_retry_on_invalid_api_key(monkeypatch) -> None:
    fake_client = FakeClient([FakeResponse(401, text="unauthorized")])

    client = LangdockLLMClient(
        api_key="sk-test",
        api_url="https://example.com",
        model="claude-sonnet-4-5-20250929",
        http_client=fake_client,
    )

    corrected, ok = client.correct_text("Teh strategc obiectives")

    assert ok is False
    assert corrected == "Teh strategc obiectives"
    assert fake_client.calls == 1


def test_langdock_client_retries_transient_errors(monkeypatch) -> None:
    responses = [
        FakeResponse(500, text="server error"),
        FakeResponse(500, text="server error"),
        FakeResponse(200, {"content": [{"type": "text", "text": "Fixed text"}]}),
    ]
    fake_client = FakeClient(responses)

    client = LangdockLLMClient(
        api_key="sk-test",
        api_url="https://example.com",
        model="claude-sonnet-4-5-20250929",
        http_client=fake_client,
    )

    corrected, ok = client.correct_text("Teh")

    assert ok is True
    assert corrected == "Fixed text"
    assert fake_client.calls == 3

