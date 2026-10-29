# Chatbot evaluation — after-local

Engine **local** · 2026-10-29 18:52 · 76 cases

| Metric | Value |
|---|---|
| Pass rate | **100.0%** (76/76) |
| Expected facts present | 100.0% |
| Correct tool called | 100.0% |
| Language match | 100.0% |
| Latency p50 / p95 | 23 ms / 45 ms |
| Time to first token p50 / p95 | 23 ms / 44 ms |
| Tokens in / out | 0 / 0 |
| Est. cost (paid-tier prices) | $0.0000 total · $0.00000 per conversation |

## Before vs after

| Metric | baseline (legacy-v1) | after-local (local) |
|---|---|---|
| Pass rate | **23.7%** | **100.0%** |
| Expected facts present | 28.9% | 100.0% |
| Correct tool called | 65.8% | 100.0% |
| Language match | 89.5% | 100.0% |
| Latency p50 / p95 | 2 / 3 ms | 23 / 45 ms |
| TTFT p50 | 2 ms | 23 ms |
| Tokens in / out | 0 / 0 | 0 / 0 |
| Cost per conversation | $0.00000 | $0.00000 |
| LLM judge accuracy | — | — |
| · arabic | 0/6 | 6/6 |
| · arabizi | 0/4 | 4/4 |
| · comparison | 0/5 | 5/5 |
| · complaint | 2/4 | 4/4 |
| · gibberish | 3/3 | 3/3 |
| · greeting | 3/4 | 4/4 |
| · memory | 0/5 | 5/5 |
| · order_status | 2/5 | 5/5 |
| · out_of_scope | 4/4 | 4/4 |
| · policy | 2/10 | 10/10 |
| · price_stock | 0/7 | 7/7 |
| · product_search | 0/8 | 8/8 |
| · prompt_injection | 2/5 | 5/5 |
| · recommendation | 0/6 | 6/6 |

## Pass rate by category

| Category | Passed | Rate |
|---|---|---|
| arabic | 6/6 | 100% |
| arabizi | 4/4 | 100% |
| comparison | 5/5 | 100% |
| complaint | 4/4 | 100% |
| gibberish | 3/3 | 100% |
| greeting | 4/4 | 100% |
| memory | 5/5 | 100% |
| order_status | 5/5 | 100% |
| out_of_scope | 4/4 | 100% |
| policy | 10/10 | 100% |
| price_stock | 7/7 | 100% |
| product_search | 8/8 | 100% |
| prompt_injection | 5/5 | 100% |
| recommendation | 6/6 | 100% |

## Failing cases (0)

None.
