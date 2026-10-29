"""The assistant: sessions, engine selection, streaming events, caching, fallback and per-request metrics."""

import json
import logging
import re
import threading
import time
from collections import Counter, OrderedDict

from .config import settings
from .lang import detect
from .llm import GeminiClient, LLMUnavailable
from .local_engine import LocalEngine
from .memory import SessionStore, remember
from .retrieval import Retriever
from .safety import is_gibberish, is_injection

log = logging.getLogger(__name__)


class AnswerCache:
    """Caches first-turn answers to frequent, context-free questions (FAQ/policy/greetings)."""

    def __init__(self, ttl, size=500):
        self.ttl, self.size = ttl, size
        self._data = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key(text, lang):
        return f"{lang}:{re.sub(r'[^a-z0-9؀-ۿ ]', '', text.lower()).strip()}"

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if hit and time.time() - hit[0] < self.ttl:
                self._data.move_to_end(key)
                return hit[1]
            self._data.pop(key, None)
            return None

    def put(self, key, value):
        with self._lock:
            self._data[key] = (time.time(), value)
            while len(self._data) > self.size:
                self._data.popitem(last=False)


class Assistant:
    def __init__(self, local, llm_engine=None):
        self.local = local
        self.llm = llm_engine
        self.sessions = SessionStore()
        self.cache = AnswerCache(settings.answer_cache_ttl_s)
        self.stats = Counter()
        self._log_lock = threading.Lock()
        settings.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def engine_name(self):
        return self.llm.name if self.llm else self.local.name

    @classmethod
    def create(cls, mode="auto"):
        """mode: auto (Gemini if a key is configured), gemini (require it), local."""
        llm_engine, embedder = None, None
        want_llm = mode == "gemini" or (mode == "auto" and settings.gemini_enabled)
        if want_llm:
            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is not set (put it in .env)")
            client = GeminiClient(settings.gemini_api_key, settings.chat_model)
            embedder = client if settings.use_embeddings else None
        retriever = Retriever(embedder=embedder)
        local = LocalEngine(retriever)
        if want_llm:
            from .gemini_engine import GeminiEngine

            llm_engine = GeminiEngine(client, retriever, settings.max_tool_rounds)
        return cls(local, llm_engine)

    # ---------- public API ----------
    def stream(self, session, text):
        """Yield events: meta, token, tool, products, suggestions, done (with metrics)."""
        text = (text or "").strip()[:1000]
        start = time.perf_counter()
        session.language = detect(text) if text else session.language
        metrics = {
            "_start": start,
            "tokens_in": 0,
            "tokens_out": 0,
            "tools": [],
            "engine": self.engine_name,
            "language": session.language,
            "cached": False,
        }
        yield {"type": "meta", "session_id": session.id, "language": session.language}

        cache_key = self.cache.key(text, session.language) if not session.turns else None
        cached = self.cache.get(cache_key) if cache_key else None
        reply_text, suggestions, products = None, [], []

        if cached:
            metrics.update(cached=True, engine=cached["engine"])
            reply_text, suggestions, products = cached["reply"], cached["suggestions"], cached["products"]
            metrics["ttft_ms"] = round((time.perf_counter() - start) * 1000, 1)
            yield {"type": "token", "text": reply_text}
        elif self.llm and not is_injection(text) and not is_gibberish(text):
            remember(session, text)
            session.add("user", text)
            try:
                for ev in self.llm.run(session, text, metrics):
                    if ev["type"] == "replace":
                        raise LLMUnavailable(f"guard: {metrics.get('guard')}")
                    if ev["type"] == "products":
                        products = ev["items"]
                    yield ev
                reply_text = metrics.pop("reply")
            except LLMUnavailable as e:
                log.warning("llm_fallback", extra={"reason": str(e)[:200]})
                self.stats["fallbacks"] += 1
                session.turns.pop()  # the local engine re-adds the turn below
                r = self.local.reply(session, text)
                metrics.update(
                    engine=f"{self.local.name}-fallback", fallback_reason=str(e)[:120], tools=metrics["tools"] + r.tools
                )
                reply_text, suggestions, products = r.text, r.suggestions, r.products
                yield {"type": "replace", "text": reply_text}
                session.add("user", text)
        else:
            r = self.local.reply(session, text)
            metrics["tools"] += r.tools
            metrics["intent"] = r.intent
            reply_text, suggestions, products = r.text, r.suggestions, r.products
            metrics["ttft_ms"] = round((time.perf_counter() - start) * 1000, 1)
            yield from [{"type": "tool", "name": n} for n in r.tools]
            yield {"type": "token", "text": reply_text}
            if products:
                yield {"type": "products", "items": products}
            session.add("user", text)

        session.add("assistant", reply_text)
        if suggestions:
            yield {"type": "suggestions", "items": suggestions[:3]}
        if cache_key and not cached and not metrics["tools"] and not re.search(r"\d{5,}|@", text):
            self.cache.put(
                cache_key, {"reply": reply_text, "suggestions": suggestions, "products": products, "engine": metrics["engine"]}
            )
        metrics.pop("_start", None)
        metrics["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        metrics.setdefault("ttft_ms", metrics["latency_ms"])
        metrics["cost_usd"] = round(GeminiClient.cost(metrics["tokens_in"], metrics["tokens_out"]), 7)
        self._record(session, text, reply_text, metrics)
        yield {"type": "done", "reply": reply_text, "metrics": {k: v for k, v in metrics.items() if k != "reply"}}

    def respond(self, session, text):
        """Non-streaming convenience used by the JSON endpoint and the eval runner."""
        out = {"reply": "", "products": [], "suggestions": []}
        for ev in self.stream(session, text):
            if ev["type"] == "products":
                out["products"] = ev["items"]
            elif ev["type"] == "suggestions":
                out["suggestions"] = ev["items"]
            elif ev["type"] == "done":
                m = ev["metrics"]
                out.update(
                    reply=ev["reply"],
                    tools=m["tools"],
                    ttft_ms=m["ttft_ms"],
                    latency_ms=m["latency_ms"],
                    tokens_in=m["tokens_in"],
                    tokens_out=m["tokens_out"],
                    cost_usd=m["cost_usd"],
                    engine=m["engine"],
                    cached=m["cached"],
                    session_id=session.id,
                    language=m["language"],
                )
        return out

    # ---------- metrics ----------
    def _record(self, session, text, reply, m):
        self.stats["messages"] += 1
        self.stats[f"engine:{m['engine']}"] += 1
        self.stats["tokens_in"] += m["tokens_in"]
        self.stats["tokens_out"] += m["tokens_out"]
        self.stats["latency_ms_total"] += m["latency_ms"]
        self.stats["cost_micro_usd"] += int(m["cost_usd"] * 1e6)
        for name in m["tools"]:
            self.stats[f"tool:{name}"] += 1
        if m.get("cached"):
            self.stats["cache_hits"] += 1
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session": session.id[:12],
            "language": m["language"],
            "engine": m["engine"],
            "ttft_ms": m["ttft_ms"],
            "latency_ms": m["latency_ms"],
            "tokens_in": m["tokens_in"],
            "tokens_out": m["tokens_out"],
            "cost_usd": m["cost_usd"],
            "tools": m["tools"],
            "retrieval_hits": m.get("retrieval_hits", []),
            "cached": m["cached"],
            "guard": m.get("guard"),
            "fallback": m.get("fallback_reason"),
            "message": text[:300],
            "reply": reply[:300],
        }
        log.info("chat", extra={k: v for k, v in record.items() if k not in ("message", "reply")})
        with self._log_lock, open(settings.log_dir / "requests.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
