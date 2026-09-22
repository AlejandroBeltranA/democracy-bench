from alignment.instrument import measure as M


def test_payload_is_unchanged_without_the_env_var(monkeypatch):
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT", raising=False)
    body = M.openrouter_payload("openai/gpt-4o-mini", "Q?")
    assert set(body) == {"model", "messages", "temperature", "max_tokens"}
    assert body["temperature"] == 0.8 and body["max_tokens"] == 16


def test_env_var_adds_reasoning_control_except_for_anthropic(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "none")
    assert M.openrouter_payload("openai/gpt-5.6-sol", "Q?")["reasoning"] == {"effort": "none"}
    assert "reasoning" not in M.openrouter_payload("anthropic/claude-sonnet-5", "Q?")


def test_max_tokens_override_only_raises_the_cap(monkeypatch):
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "512")
    assert M.openrouter_payload("google/gemini-3.8-flash", "Q?")["max_tokens"] == 512
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "4")
    assert M.openrouter_payload("google/gemini-3.8-flash", "Q?")["max_tokens"] == 16
