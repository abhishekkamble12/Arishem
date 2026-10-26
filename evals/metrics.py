"""
Deterministic evaluation metrics. No LLM, no network, no Django.

These complement the LLM-judged faithfulness score. They cost nothing to run,
give the same answer every time, and can be unit-tested — which a judge cannot.

  key_fact_score     did the answer contain the facts a correct answer needs?
  retrieval_ranks    did retrieval surface the right document, and how high?
  is_abstention      did the system decline to answer?
  abstention_report  how well does declining track "the corpus cannot answer this"?
"""

import re
import statistics

# Typographic dashes and spaces models emit ("Full‑time", "9 a.m.") would defeat
# substring matching, so fold them to ASCII before comparing.
_FOLD = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-",
                       "—": "-", " ": " ", " ": " ", "’": "'"})


def normalise(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").translate(_FOLD).lower()).strip()


def _matches(alternative: str, text: str) -> bool:
    """
    Whole-token match, so that "5" does not match "15" and "uv" does not match
    "uvicorn". A trailing "*" makes it a prefix: "quarter*" matches "quarterly".
    """
    alt = normalise(alternative)
    prefix = alt.endswith("*")
    alt = alt.rstrip("*")
    if not alt:
        return False
    pattern = re.escape(alt)
    if alt[0].isalnum():
        pattern = r"(?<![a-z0-9])" + pattern
    if alt[-1].isalnum() and not prefix:
        pattern += r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def contains_any(answer, phrases) -> bool:
    """Whether any phrase appears in the answer, by the same whole-token rule."""
    text = normalise(answer)
    return any(_matches(p, text) for p in phrases or ())


def key_fact_score(answer, key_facts, forbidden=()):
    """
    Fraction of required facts present in the answer, or None if the question
    has none (unanswerable questions).

    key_facts is a list of groups; a group is satisfied if ANY of its
    alternatives appears ([["7", "seven"], ["year*"]] needs a seven AND a year).
    Any forbidden phrase scores 0 outright — that is how an answer hijacked by a
    prompt injection is caught even if it also repeats the right number.
    """
    if not key_facts:
        return None
    if contains_any(answer, forbidden):
        return 0.0
    text = normalise(answer)
    hit = sum(1 for group in key_facts if any(_matches(alt, text) for alt in group))
    return hit / len(key_facts)


def retrieval_ranks(retrieved_sources, relevant_sources):
    """
    (hit, reciprocal_rank, recall) for one question.

    hit       a relevant document appears anywhere in the top-k
    rr        1 / rank of the first relevant chunk (0 if none) — averaged, this is MRR
    recall    share of the relevant documents that appear at all, which matters for
              multi-hop questions that need two documents
    """
    if not relevant_sources:
        return None, None, None
    relevant = set(relevant_sources)
    rr = 0.0
    for rank, source in enumerate(retrieved_sources, start=1):
        if source in relevant:
            rr = 1.0 / rank
            break
    found = relevant & set(retrieved_sources)
    return bool(found), rr, len(found) / len(relevant)


# How an LLM declines on its own, after retrieval passed the threshold. Without
# this, "the documents don't specify" in reply to an unanswerable question would
# be scored as a hallucination. A pattern rather than a phrase list, because the
# phrasings multiply: does not / do not / doesn't / don't x specify / mention / ...
_DECLINE_VERBS = r"(specify|specified|mention|mentioned|state|stated|address|addressed|provide|" \
                 r"provided|include|included|contain|contained|cover|covered|say|list|listed|define|defined)"
_ABSTAIN_PATTERNS = [
    re.compile(r"\b(does|do|did|is|are|was|were)\s*(not|n't)\s+(\w+\s+)?" + _DECLINE_VERBS + r"\b"),
    re.compile(r"\b(not|never)\s+" + _DECLINE_VERBS + r"\b"),
    re.compile(r"\bno\s+(information|mention|details|data|reference|indication|record)\b"),
    re.compile(r"\b(not|n't)\s+(have|contain)\s+enough\b"),
    re.compile(r"\bnot enough (relevant |)(information|context)\b"),
    re.compile(r"\b(cannot|can't|unable to|could not|couldn't)\s+(find|determine|answer|locate)\b"),
]


def is_abstention(answer, refused=False) -> bool:
    if refused:
        return True
    text = normalise(answer)
    return any(p.search(text) for p in _ABSTAIN_PATTERNS)


def abstention_report(rows):
    """
    How well declining to answer tracks the truth.

    precision       of the questions it declined, how many really were unanswerable
    recall          of the unanswerable questions, how many it declined
    false_abstain   share of answerable questions it wrongly declined
    hallucinated    share of unanswerable questions it answered anyway
    """
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    abstained = [r for r in rows if r["abstained"]]
    true_abstain = sum(1 for r in abstained if not r["answerable"])
    return {
        "precision": true_abstain / len(abstained) if abstained else None,
        "recall": true_abstain / len(unanswerable) if unanswerable else None,
        "false_abstain": (sum(1 for r in answerable if r["abstained"]) / len(answerable)
                          if answerable else None),
        "hallucinated": (sum(1 for r in unanswerable if not r["abstained"]) / len(unanswerable)
                         if unanswerable else None),
        "abstained_by_threshold": sum(1 for r in abstained if r.get("refused")),
        "abstained_by_model": sum(1 for r in abstained if not r.get("refused")),
    }


def mean_or_none(values):
    values = [v for v in values if v is not None and v == v]  # drop None and NaN
    return statistics.mean(values) if values else None
