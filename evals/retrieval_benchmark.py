"""
Retrieval methods compared, on a public benchmark and on this project's golden set.

    python evals/retrieval_benchmark.py

The golden set alone cannot choose a retrieval method: with 19 chunks and a top-5,
almost anything finds the right document (dense retrieval already gets 52/53). So
the main comparison is BEIR SciFact - 5,183 scientific abstracts, 300 test
questions, relevance judged by people - which is large enough for the methods to
differ. It is downloaded once (~3 MB) into evals/.data/, which git ignores.

Methods:
  dense          production today: all-MiniLM-L6-v2, cosine similarity
  bm25           keyword scoring (k1=0.9, b=0.4, the Anserini settings BEIR uses)
  hybrid         reciprocal rank fusion of dense and bm25 (k=60)
  dense+rerank   dense top-20, reordered by a cross-encoder
  hybrid+rerank  hybrid top-20, reordered by the same cross-encoder

Writes evals/RETRIEVAL_BENCHMARK.md. Needs no API key and makes no LLM calls.
"""

import collections
import csv
import io
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.request
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, ".data")
SCIFACT_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip"
DENSE_MODEL = "all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_DEPTH = 20
TOKEN = re.compile(r"\w+")

sys.path.insert(0, HERE)
from metrics import retrieval_ranks  # noqa: E402


# ── data ─────────────────────────────────────────────────────────────────────
def load_scifact():
    folder = os.path.join(DATA, "scifact")
    if not os.path.isdir(folder):
        os.makedirs(DATA, exist_ok=True)
        print(f"downloading {SCIFACT_URL}")
        with urllib.request.urlopen(SCIFACT_URL, timeout=120) as resp:
            zipfile.ZipFile(io.BytesIO(resp.read())).extractall(DATA)
    with open(os.path.join(folder, "corpus.jsonl"), encoding="utf-8") as fh:
        docs = [json.loads(line) for line in fh]
    with open(os.path.join(folder, "queries.jsonl"), encoding="utf-8") as fh:
        queries = {q["_id"]: q["text"] for q in map(json.loads, fh)}
    qrels = collections.defaultdict(set)
    with open(os.path.join(folder, "qrels", "test.tsv"), encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if int(row["score"]) > 0:
                qrels[row["query-id"]].add(row["corpus-id"])
    ids = [d["_id"] for d in docs]
    texts = [f"{d['title']}. {d['text']}" for d in docs]
    tests = [(queries[q], rel) for q, rel in qrels.items()]
    return ids, texts, tests


def load_golden():
    """pcaps/ chunked exactly as the eval harness (and so production) chunks it."""
    import run_eval  # sets up Django; only needed for this half

    chunks, _ = run_eval.load_corpus()
    with open(os.path.join(HERE, "golden_set.json"), encoding="utf-8") as fh:
        golden = [q for q in json.load(fh) if q["answerable"]]
    return ([c.metadata["source"] for c in chunks], [c.page_content for c in chunks],
            [(q["question"], set(q["relevant_sources"])) for q in golden])


# ── retrievers ───────────────────────────────────────────────────────────────
class BM25:
    def __init__(self, texts, k1=0.9, b=0.4):
        self.k1, self.b = k1, b
        self.docs = [collections.Counter(TOKEN.findall(t.lower())) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = statistics.mean(self.lengths)
        df = collections.Counter(term for d in self.docs for term in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.postings = collections.defaultdict(list)
        for i, d in enumerate(self.docs):
            for term, tf in d.items():
                self.postings[term].append((i, tf))

    def scores(self, query):
        out = collections.defaultdict(float)
        for term in set(TOKEN.findall(query.lower())):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in self.postings[term]:
                norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg)
                out[i] += idf * tf * (self.k1 + 1) / (tf + norm)
        return out


def top(scores, k):
    if isinstance(scores, dict):
        return [i for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:k]]
    return list(np.argsort(-scores)[:k])


def rrf(*rankings, k=60):
    fused = collections.defaultdict(float)
    for ranking in rankings:
        for rank, i in enumerate(ranking, start=1):
            fused[i] += 1 / (k + rank)
    return [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])]


# ── metrics ──────────────────────────────────────────────────────────────────
def ndcg_at_10(ranked_ids, relevant):
    # The golden set ranks chunks but judges documents, so one document can appear
    # several times; count only its first appearance, or nDCG could exceed 1.
    ranked_ids = list(dict.fromkeys(ranked_ids))
    dcg = sum(1 / math.log2(r + 1) for r, d in enumerate(ranked_ids[:10], start=1) if d in relevant)
    ideal = sum(1 / math.log2(r + 1) for r in range(1, min(len(relevant), 10) + 1))
    return dcg / ideal


def evaluate(ids, texts, tests, dense_model, reranker, label):
    t = time.perf_counter()
    doc_vecs = dense_model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    bm25 = BM25(texts)
    print(f"[{label}] indexed {len(texts)} documents in {time.perf_counter() - t:.0f}s")

    methods = ["dense", "bm25", "hybrid", "dense+rerank", "hybrid+rerank"]
    results = {m: collections.defaultdict(list) for m in methods}
    for question, relevant in tests:
        timings = {}
        t = time.perf_counter()
        dense_rank = top(doc_vecs @ dense_model.encode(question, normalize_embeddings=True), 100)
        timings["dense"] = time.perf_counter() - t
        t = time.perf_counter()
        bm25_rank = top(bm25.scores(question), 100)
        timings["bm25"] = time.perf_counter() - t
        hybrid_rank = rrf(dense_rank, bm25_rank)
        timings["hybrid"] = timings["dense"] + timings["bm25"]
        ranks = {"dense": dense_rank, "bm25": bm25_rank, "hybrid": hybrid_rank}
        for base in ("dense", "hybrid"):
            t = time.perf_counter()
            candidates = ranks[base][:RERANK_DEPTH]
            order = np.argsort(-reranker.predict([(question, texts[i]) for i in candidates],
                                                 show_progress_bar=False))
            ranks[f"{base}+rerank"] = [candidates[j] for j in order] + ranks[base][RERANK_DEPTH:]
            timings[f"{base}+rerank"] = timings[base] + time.perf_counter() - t
        for m in methods:
            ranked = [ids[i] for i in ranks[m]]
            hit, rr, _ = retrieval_ranks(ranked[:5], relevant)
            results[m]["hit@5"].append(hit)
            results[m]["mrr@5"].append(rr)
            results[m]["ndcg@10"].append(ndcg_at_10(ranked, relevant))
            results[m]["ms"].append(timings[m] * 1000)
    return {m: {k: statistics.mean(v) for k, v in r.items()} | {"p95_ms": float(np.percentile(r["ms"], 95))}
            for m, r in results.items()}


def main():
    from sentence_transformers import CrossEncoder, SentenceTransformer

    dense_model = SentenceTransformer(DENSE_MODEL)
    reranker = CrossEncoder(RERANK_MODEL)
    suites = {
        "BEIR SciFact (5,183 documents, 300 questions)": load_scifact(),
        "Golden set (19 chunks, 53 answerable questions)": load_golden(),
    }
    report = [
        "# Retrieval benchmark", "",
        "_Generated by `evals/retrieval_benchmark.py` - do not edit by hand._", "",
        f"Dense model `{DENSE_MODEL}` (production). Reranker `{RERANK_MODEL}` over the top "
        f"{RERANK_DEPTH}. Latency is per question on this machine's CPU, retrieval only "
        f"(no LLM), and excludes the network hop to Qdrant.", "",
    ]
    for name, (ids, texts, tests) in suites.items():
        scores = evaluate(ids, texts, tests, dense_model, reranker, name.split(" (")[0])
        report += [f"## {name}", "",
                   "| Method | nDCG@10 | Hit@5 | MRR@5 | Mean ms | p95 ms |", "|---|---|---|---|---|---|"]
        for m, s in scores.items():
            report.append(f"| {m} | {s['ndcg@10']:.3f} | {s['hit@5']:.3f} | {s['mrr@5']:.3f} | "
                          f"{s['ms']:.0f} | {s['p95_ms']:.0f} |")
        report.append("")
        print("\n".join(report[-len(scores) - 4:]))
    with open(os.path.join(HERE, "RETRIEVAL_BENCHMARK.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report))


if __name__ == "__main__":
    main()
