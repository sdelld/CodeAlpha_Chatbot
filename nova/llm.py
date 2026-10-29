"""Gemini client wrapper: timeouts, retries with exponential backoff, token/cost accounting, embeddings."""

import json
import logging
import random
import re
import time

from .config import settings

log = logging.getLogger(__name__)
RETRYABLE = {408, 429, 500, 502, 503, 504}


class LLMUnavailable(Exception):
    """Raised after retries are exhausted; callers fall back to the local engine."""


def _status(exc):
    return getattr(exc, "code", None) or getattr(exc, "status_code", None)


def with_retries(fn, what, max_retries=None):
    attempts = (max_retries if max_retries is not None else settings.max_retries) + 1
    delay = 0.8
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # SDK raises errors.APIError (with .code) and httpx timeouts
            status = _status(e)
            timeout = "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower()
            if attempt == attempts or not (status in RETRYABLE or timeout):
                log.warning("llm_failed", extra={"what": what, "status": status, "attempt": attempt, "error": str(e)[:200]})
                raise LLMUnavailable(f"{what} failed: {status or type(e).__name__}") from e
            # Respect server-suggested backoff when present ("retry in 12s"), else exponential + jitter.
            hint = re.search(r"retry(?:Delay)?[^0-9]{0,12}(\d+(?:\.\d+)?)s", str(e))
            wait = min(float(hint.group(1)), 20) if hint else delay + random.uniform(0, delay / 2)  # noqa: S311
            log.info("llm_retry", extra={"what": what, "status": status, "attempt": attempt, "wait_s": round(wait, 2)})
            time.sleep(wait)
            delay *= 2


class GeminiClient:
    def __init__(self, api_key, model, embedding_model=None):
        from google import genai
        from google.genai import types

        self.types = types
        self.model = model
        self.embedding_model = embedding_model or settings.embedding_model
        # SDK-level retries off: retries are handled above so they're logged and bounded consistently.
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(settings.timeout_s * 1000)))

    @classmethod
    def from_env(cls, model_env="GEMINI_MODEL"):
        if not settings.gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not set")
        model = settings.judge_model if model_env == "GEMINI_JUDGE_MODEL" else settings.chat_model
        return cls(settings.gemini_api_key, model)

    @staticmethod
    def cost(tokens_in, tokens_out):
        return tokens_in / 1e6 * settings.price_in + tokens_out / 1e6 * settings.price_out

    def stream(self, contents, system, tools=None, temperature=0.3, max_output_tokens=900):
        """Yield raw stream chunks. Retries only happen before the first chunk arrives."""
        t = self.types
        config = t.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=[t.Tool(function_declarations=tools)] if tools else None,
            automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),
        )

        def start():
            # The request is sent when the first chunk is read, so that's the step that must be retried.
            it = iter(self.client.models.generate_content_stream(model=self.model, contents=contents, config=config))
            return it, next(it, None)

        iterator, first = with_retries(start, "generate_stream")
        if first is not None:
            yield first
        try:
            yield from iterator
        except Exception as e:
            raise LLMUnavailable(f"stream interrupted: {type(e).__name__}") from e

    def generate_json(self, prompt, temperature=0.0):
        t = self.types
        config = t.GenerateContentConfig(temperature=temperature, response_mime_type="application/json", max_output_tokens=400)
        resp = with_retries(
            lambda: self.client.models.generate_content(model=self.model, contents=prompt, config=config), "generate_json"
        )
        text = resp.text or "{}"
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0) if m else text)

    def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
        t = self.types
        out = []
        for i in range(0, len(texts), 50):
            batch = texts[i : i + 50]
            resp = with_retries(
                lambda b=batch: self.client.models.embed_content(
                    model=self.embedding_model, contents=b, config=t.EmbedContentConfig(task_type=task, output_dimensionality=768)
                ),
                "embed",
            )
            out += [e.values for e in resp.embeddings]
        return out
