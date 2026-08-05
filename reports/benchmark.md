# Arishem Performance Test Results

## Test Setup
- Date: 2026-08-05
- Environment: Local Docker, SQLite fallback, Qdrant Cloud free tier, Groq API (Llama 3.3 70B)
- Test corpus: SOP-104_Data_Retention_Policy.pdf
- Confidence threshold: 0.30
- Top-K: 5

## Test Results

| Operation | Latency | Status | Confidence | Insight |
|---|---|---|---|---|
| Ingestion (1 PDF) | 2,222ms | ✅ Success | N/A | PDF chunked and stored in Qdrant |
| Query Q1 (in-domain) | 1,949ms | ✅ Success | 0.7258 | Correctly answered "90 days", cited SOP-104 |
| Query Q2 (in-domain) | 914ms | ✅ Success | 0.3707 | Correctly answered compliance officer email, cited SOP-104 |
| Query Q3 (OOD) | 625ms | ✅ Success (rejection) | 0.0986 | Bypassed LLM call due to confidence < 0.30 |

## Key Findings

1. **OOD rejection works as designed.** Out-of-domain query confidence (0.0986) was well below threshold (0.30), system correctly skipped LLM generation.
2. **Citation grounding holds.** Both in-domain queries returned source citations (SOP-104_Data_Retention_Policy.pdf).
3. **Latency range observed:** 625ms–1,949ms. Median ~1.4s. Cold-start cost amortized after first query.
4. **Cost estimate:** Based on Groq pricing (~$0.30/1M tokens) and ~1K tokens per query, ~$0.0003/query for inference.

## Files
- `reports/test_run.txt` — raw query output
- `reports/benchmark.md` — this file
- `pcaps/SOP-104_Data_Retention_Policy.pdf` — input documents
