"""Tests de la couche LLM : parsing Mistral, factory, retry."""

import pytest

from config import Settings
from llm.base import LLMError, LLMTransientError
from llm.factory import build_llm_provider
from llm.mistral import _parse_mistral_response
from reports.retry import with_retry


# -- factory ---------------------------------------------------------------


def test_factory_mistral_default():
    p = build_llm_provider(Settings(llm_provider="mistral", mistral_api_key="k"))
    assert p.name == "mistral"


def test_factory_anthropic():
    p = build_llm_provider(Settings(llm_provider="anthropic", anthropic_api_key="k"))
    assert p.name == "anthropic"


def test_factory_unknown_raises():
    with pytest.raises(LLMError):
        build_llm_provider(Settings(llm_provider="doesnotexist"))


# -- parsing reponse Mistral ----------------------------------------------


def test_parse_mistral_ok():
    data = {
        "choices": [
            {"message": {"content": '{"cr":"x"}'}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    resp = _parse_mistral_response(data, "mistral-large-latest")
    assert resp.text == '{"cr":"x"}'
    assert resp.truncated is False
    assert resp.usage["total_tokens"] == 30


def test_parse_mistral_truncated():
    data = {"choices": [{"message": {"content": "x"}, "finish_reason": "length"}]}
    assert _parse_mistral_response(data, "m").truncated is True


def test_parse_mistral_empty_raises():
    with pytest.raises(LLMError):
        _parse_mistral_response({"choices": []}, "m")


# -- retry -----------------------------------------------------------------


async def test_retry_succeeds_after_transient():
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise LLMTransientError("boom")
        return "ok"

    result = await with_retry(flaky, max_retries=3, base_delay=0.0, label="test")
    assert result == "ok"
    assert attempts["n"] == 2


async def test_retry_gives_up():
    async def always_fail():
        raise LLMTransientError("boom")

    with pytest.raises(LLMTransientError):
        await with_retry(always_fail, max_retries=1, base_delay=0.0, label="test")


async def test_retry_non_transient_not_retried():
    attempts = {"n": 0}

    async def hard_fail():
        attempts["n"] += 1
        raise LLMError("fatal")

    with pytest.raises(LLMError):
        await with_retry(hard_fail, max_retries=3, base_delay=0.0, label="test")
    assert attempts["n"] == 1
