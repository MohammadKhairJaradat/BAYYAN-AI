"""Provider adapter contracts use only local fakes; no paid API calls."""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.integrations.ai import adapters, google
from app.integrations.ai.registry import SUPPORTED_CHAT_MODELS, TIER_CHAT_ACCESS


def test_tier_models_are_registered():
    for access in TIER_CHAT_ACCESS.values():
        for provider, models in access.items():
            assert models <= SUPPORTED_CHAT_MODELS[provider]


def test_google_sdk_call_has_timeout_and_closes_client(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *, api_key, http_options):
            assert api_key == "test-key"
            assert http_options.timeout == 30_000
            self.models = SimpleNamespace(generate_content=self.generate_content)

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="ok")

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(google.genai, "Client", FakeClient)
    result = google.generate(
        api_key="test-key", model="gemini-test", prompt="Read this",
        system_instruction="Respond briefly", max_output_tokens=100,
        media=b"%PDF-test", media_mime_type="application/pdf",
    )
    assert result == "ok"
    assert calls[0]["contents"][1].inline_data.mime_type == "application/pdf"
    assert calls[0]["config"].system_instruction == "Respond briefly"
    assert calls[1] == "closed"


def test_openai_adapter_success_and_no_sdk_retry(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))])

    monkeypatch.setattr("openai.OpenAI", FakeClient)
    assert adapters.complete_text("openai", model="gpt-4o", system="S", user="U", max_tokens=100) == "answer"
    assert calls[0]["max_retries"] == 0
    assert calls[0]["timeout"] == 30
    assert calls[1]["max_completion_tokens"] == 100


@pytest.mark.parametrize("error,kind,status", [
    (TimeoutError("timed out"), "timeout", None),
    (type("RateLimit", (Exception,), {"status_code": 429})("busy"), "rate_limit", 429),
    (ValueError("bad response"), "unavailable", None),
])
def test_google_adapter_normalizes_provider_errors(monkeypatch, error, kind, status):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    def fail(**_kwargs):
        raise error

    monkeypatch.setattr(adapters, "google_generate", fail)
    with pytest.raises(adapters.AIProviderError) as caught:
        adapters.complete_text("gemini", model="gemini-2.5-flash", system="S", user="U", max_tokens=100)
    assert caught.value.kind == kind
    assert caught.value.status_code == status
    assert "test-key" not in str(caught.value)


def test_google_adapter_rejects_malformed_output(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(adapters, "google_generate", lambda **_kwargs: "")
    with pytest.raises(adapters.AIProviderError) as caught:
        adapters.complete_text("gemini", model="gemini-2.5-flash", system="S", user="U", max_tokens=100)
    assert caught.value.kind == "malformed_response"


@pytest.mark.parametrize("provider", ["anthropic", "openai", "groq", "gemini"])
@pytest.mark.parametrize("outcome,expected", [
    ("success", None), ("timeout", "timeout"),
    ("rate_limit", "rate_limit"), ("malformed", "malformed_response"),
])
def test_each_text_provider_contract(monkeypatch, provider, outcome, expected):
    monkeypatch.setattr(settings, {
        "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
        "groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY",
    }[provider], "test-key")

    def answer():
        if outcome == "timeout":
            raise TimeoutError("timed out")
        if outcome == "rate_limit":
            error = RuntimeError("busy")
            error.status_code = 429
            raise error
        return "" if outcome == "malformed" else "answer"

    if provider == "gemini":
        monkeypatch.setattr(adapters, "google_generate", lambda **_kwargs: answer())
    else:
        class FakeClient:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.openai_create))
                self.messages = SimpleNamespace(create=self.anthropic_create)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def openai_create(self, **_kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer()))])

            def anthropic_create(self, **_kwargs):
                return SimpleNamespace(content=[SimpleNamespace(text=answer())])

        if provider == "anthropic":
            monkeypatch.setattr("anthropic.Anthropic", FakeClient)
        else:
            monkeypatch.setattr("openai.OpenAI", FakeClient)

    call = lambda: adapters.complete_text(provider, model="test-model", system="S", user="U", max_tokens=10)
    if expected is None:
        assert call() == "answer"
    else:
        with pytest.raises(adapters.AIProviderError) as caught:
            call()
        assert caught.value.kind == expected
