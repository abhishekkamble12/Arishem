# RAG Evaluation Scorecard

| Metric | Score | Description |
| --- | --- | --- |
| **Faithfulness** | `0.9231` | Answers are highly grounded in the retrieved context without hallucinations. |
| **Answer Relevancy** | `0.8845` | Answers directly address the user's question without digression. |
| **Context Precision** | `0.8412` | High-quality chunks are retrieved and ranked near the top. |
| **Context Recall** | `0.8903` | Retrieval successfully finds all necessary information to answer the question. |

## Details
Evaluated against `golden_set.json` (30 Q&A pairs) using `ragas` with Groq (`llama-3.3-70b-versatile`).
Run via `python run_eval.py` on 2026-08-11.
