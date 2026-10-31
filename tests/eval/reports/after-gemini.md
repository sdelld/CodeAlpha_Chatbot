# Chatbot evaluation — after-gemini

Engine **gemini:gemini-3.5-flash-lite** · 2026-10-31 16:13 · 76 cases

| Metric | Value |
|---|---|
| Pass rate | **90.8%** (69/76) |
| Expected facts present | 100.0% |
| Correct tool called | 90.8% |
| Language match | 100.0% |
| Latency p50 / p95 | 2094 ms / 4686 ms |
| Time to first token p50 / p95 | 1663 ms / 4134 ms |
| Tokens in / out | 154,767 / 7,398 |
| Est. cost (paid-tier prices) | $0.0649 total · $0.00085 per conversation |
| LLM judge (1-5): accuracy / helpfulness / tone / language | 5 / 5 / 5 / 5 (28 cases) |

## Pass rate by category

| Category | Passed | Rate |
|---|---|---|
| arabic | 4/6 | 67% |
| arabizi | 4/4 | 100% |
| comparison | 4/5 | 80% |
| complaint | 4/4 | 100% |
| gibberish | 3/3 | 100% |
| greeting | 4/4 | 100% |
| memory | 5/5 | 100% |
| order_status | 5/5 | 100% |
| out_of_scope | 4/4 | 100% |
| policy | 10/10 | 100% |
| price_stock | 6/7 | 86% |
| product_search | 6/8 | 75% |
| prompt_injection | 5/5 | 100% |
| recommendation | 5/6 | 83% |

## Failing cases (7)

- **search-1** (product_search) `Do you have noise cancelling headphones?` — tool not called (got none)  
  > Yes, we do! Here are two great options for noise-cancelling headphones:  • **Pulse ANC 700** – 7,999 EGP     * Over-ear wireless with adaptive ANC and up to 40 hours of battery life. • **Pulse Buds Pro 2** – 4,499 EGP   
- **search-4** (product_search) `what smartwatches do you sell?` — tool not called (got none)  
  > We currently carry two great smartwatches:  • **Orbit Watch 3** (9,499 EGP): Features a 1.4" AMOLED screen, dual-band GPS, advanced health tracking (heart rate, SpO2, ECG, sleep), 3 days of battery life, and 5 ATM water 
- **cmp-4** (comparison) `Orbit Watch 3 or Orbit Band 8 for running outdoors?` — tool not called (got none)  
  > For running outdoors, I’d pick the **Orbit Watch 3** (9,499 EGP).   Here is how they compare for your runs: * **Orbit Watch 3 (9,499 EGP):** Features **built-in dual-band GPS**, so you can track your running routes accur
- **rec-4** (recommendation) `which headphones are best for long flights?` — tool not called (got none)  
  > For long flights, the **Pulse ANC 700** is the best choice from our lineup.   • **Pulse ANC 700** – 7,999 EGP   • Adaptive ANC to block out cabin noise   • 40-hour battery life for ultra-long flights  I'd pick the Pulse 
- **price-5** (price_stock) `when will the Orbit Lite 5G be back?` — tool not called (got none)  
  > The Orbit Lite 5G [PH-004] is currently out of stock and expected to be back on November 12, 2026.   If you're looking for a phone right away, would you like me to check out other available phones for you?
- **ar-1** (arabic) `عندكم سماعات بعزل ضوضاء؟` — tool not called (got none)  
  > أهلاً بحضرتك في نوفا للإلكترونيات!   أنا نوڤا، وتحت أمرك في أي استفسار. عندنا كذا اختيار ممتاز لسماعات بعزل الضوضاء:  • **Pulse ANC 700** بسعر 7,999 جنيه — سماعة فوق الأذن لاسلكية مع عزل ضوضاء تكيفي وبطارية 40 ساعة. ممتا
- **ar-5** (arabic) `عايز لابتوب للجامعة وميزانيتي ٢٥ ألف` — tool not called (got none)  
  > أهلاً بيك! عندنا خيار ممتاز ومناسب جداً لميزانيتك والجامعة:  • **Vertex Study 15** من Vertex: بسعر **24,999 جنيه**. المواصفات: شاشة 15.6 بوصة FHD IPS، معالج Vertex V5، ورام 8 جيجابايت مع مساحة تخزين 512 جيجابايت SSD. ممت
