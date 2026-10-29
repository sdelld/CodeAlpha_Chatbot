# Chatbot evaluation — holdout-local

Engine **local** · 2026-10-29 18:38 · 30 cases

| Metric | Value |
|---|---|
| Pass rate | **93.3%** (28/30) |
| Expected facts present | 96.7% |
| Correct tool called | 96.7% |
| Language match | 100.0% |
| Latency p50 / p95 | 26 ms / 38 ms |
| Time to first token p50 / p95 | 26 ms / 38 ms |
| Tokens in / out | 0 / 0 |
| Est. cost (paid-tier prices) | $0.0000 total · $0.00000 per conversation |

## Pass rate by category

| Category | Passed | Rate |
|---|---|---|
| arabic | 2/2 | 100% |
| arabizi | 2/2 | 100% |
| comparison | 2/2 | 100% |
| complaint | 1/1 | 100% |
| greeting | 2/2 | 100% |
| memory | 2/2 | 100% |
| order_status | 1/2 | 50% |
| out_of_scope | 1/1 | 100% |
| policy | 4/4 | 100% |
| price_stock | 2/3 | 67% |
| product_search | 4/4 | 100% |
| prompt_injection | 2/2 | 100% |
| recommendation | 3/3 | 100% |

## Failing cases (2)

- **h-price-2** (price_stock) `can I find the Orbit Fold Z in Alexandria?` — tool not called (got ['get_product'])  
  > The **Orbit Fold Z** costs **69,999 EGP**. In stock. Warranty: 12 months. Key specs — screen: 7.6" foldable AMOLED + 6.3" cover; chip: Orbit O9; ram: 12 GB; storage: 512 GB; camera: 50 MP main + 12 MP ultrawide + 10 MP 3
- **h-order-2** (order_status) `my order hasn't arrived yet` — missing: order number | nv12345  
  > Standard delivery costs 75 EGP and is free on orders of 2,500 EGP or more. Express same-day delivery in Cairo and Giza costs 150 EGP for orders placed before 2 PM.
