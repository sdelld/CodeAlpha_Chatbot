"""LLM engine: retrieval-augmented Gemini with function calling and streaming.

Per turn: retrieve top chunks -> build prompt (system rules + CONTEXT + MEMORY + recent turns) -> stream the model;
when the model calls a tool, run it and continue; text chunks are yielded to the client as they arrive.
After the answer, every price in it is checked against the data; an ungrounded answer is replaced.
"""

import json
import time

from . import tools
from .knowledge import get_knowledge
from .llm import GeminiClient
from .memory import remember_products
from .prompts import CANARY, context_block, system_prompt
from .safety import ungrounded_prices


class GeminiEngine:
    def __init__(self, client: GeminiClient, retriever, max_tool_rounds=4):
        self.client = client
        self.retriever = retriever
        self.kb = get_knowledge()
        self.max_tool_rounds = max_tool_rounds
        self.name = f"gemini:{client.model}"

    def build_contents(self, session, text, hits):
        t = self.client.types
        contents = []
        for turn in session.recent()[:-1]:  # the current user message is added below with context
            role = "user" if turn["role"] == "user" else "model"
            contents.append(t.Content(role=role, parts=[t.Part(text=turn["text"])]))
        block = context_block(hits, session.fact_sheet(), session.language)
        contents.append(t.Content(role="user", parts=[t.Part(text=f"{block}\n\nCUSTOMER MESSAGE:\n{text}")]))
        return contents

    def run(self, session, text, metrics):
        """Generator of events: {"type": "token"|"tool"|"products"|"replace", ...}. Fills `metrics`."""
        t = self.client.types
        t0 = time.perf_counter()
        hits = self.retriever.search(text, k=6)
        metrics["retrieval_hits"] = [h["doc"].id for h in hits]
        metrics["retrieval_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        contents = self.build_contents(session, text, hits)
        allowed = set(self.kb.known_amounts)
        products = {}
        answer = []

        for _round in range(self.max_tool_rounds + 1):
            model_parts, calls = [], []
            for chunk in self.client.stream(
                contents, system_prompt(), tools=tools.DECLARATIONS if _round < self.max_tool_rounds else None
            ):
                usage = getattr(chunk, "usage_metadata", None)
                if usage and usage.prompt_token_count:
                    metrics["_round_in"] = usage.prompt_token_count
                    metrics["_round_out"] = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                cand = (chunk.candidates or [None])[0]
                for part in cand.content.parts if cand and cand.content and cand.content.parts else []:
                    model_parts.append(part)  # keep everything (incl. thought signatures) to send back
                    if part.function_call:
                        calls.append(part.function_call)
                    elif part.text and not getattr(part, "thought", False):
                        if "ttft_ms" not in metrics:
                            metrics["ttft_ms"] = round((time.perf_counter() - metrics["_start"]) * 1000, 1)
                        answer.append(part.text)
                        yield {"type": "token", "text": part.text}
            metrics["tokens_in"] += metrics.pop("_round_in", 0)
            metrics["tokens_out"] += metrics.pop("_round_out", 0)
            if not calls:
                break
            contents.append(t.Content(role="model", parts=model_parts))
            responses = []
            for call in calls:
                args = dict(call.args or {})
                result = tools.call(call.name, args)
                metrics["tools"].append(call.name)
                yield {"type": "tool", "name": call.name, "args": args}
                allowed |= _amounts_in(result)
                for card in _cards_in(result):
                    products[card["id"]] = card
                responses.append(t.Part.from_function_response(name=call.name, response={"result": result}))
            contents.append(t.Content(role="user", parts=responses))

        reply = "".join(answer).strip()
        if products:
            remember_products(session, list(products)[:4])
            yield {"type": "products", "items": list(products.values())[:4]}
        bad = ungrounded_prices(reply, allowed)
        leaked = CANARY.lower() in reply.lower()
        if bad or leaked or not reply:
            metrics["guard"] = {"ungrounded_prices": bad, "leak": leaked, "empty": not reply}
            yield {"type": "replace", "reason": "guard"}
            return
        metrics["reply"] = reply


def _amounts_in(result):
    found = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, int) and x >= 100:
            found.add(x)

    walk(result)
    return found


def _cards_in(result):
    items = []
    if isinstance(result, dict):
        if "price_egp" in result and "id" in result:
            items.append(
                {
                    k: v
                    for k, v in result.items()
                    if k in ("id", "name", "brand", "category", "price_egp", "in_stock", "key_specs", "restock_date")
                }
            )
        for key in ("results", "products"):
            for r in result.get(key, []) or []:
                if isinstance(r, dict) and "price_egp" in r:
                    card = {
                        k: v
                        for k, v in r.items()
                        if k in ("id", "name", "brand", "category", "price_egp", "in_stock", "key_specs", "restock_date")
                    }
                    if "key_specs" not in card and "specs" in r:
                        card["key_specs"] = dict(list(r["specs"].items())[:3])
                    items.append(card)
    return items


__all__ = ["GeminiEngine", "json"]
