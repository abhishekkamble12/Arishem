"""
Negative control for the RAGAS faithfulness judge.

    python evals/judge_control.py            # needs GROQ_API_KEY

When every real answer scores 1.0 on faithfulness, that number means something
only if the same judge scores a fabricated answer low. This feeds the judge four
answers whose truth is known in advance — one faithful, one fully invented, one
half invented, one with a wrong figure — and exits non-zero if it rubber-stamps
any of the bad ones.

Run it whenever the judge model changes. A judge that cannot fail is not a judge.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

import dotenv  # noqa: E402

dotenv.load_dotenv(os.path.join(HERE, "..", "backend", "backend", ".env"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
os.environ.setdefault("SECRET_KEY", "eval-harness-only")

import django  # noqa: E402

django.setup()

from datasets import Dataset  # noqa: E402
from langchain_groq import ChatGroq  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import faithfulness  # noqa: E402
from ragas.run_config import RunConfig  # noqa: E402

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "openai/gpt-oss-120b")

CONTEXT = [
    "SOP-104 Data Retention Policy. All API prediction logs must be retained for "
    "exactly 90 days. Audits: External audits will be conducted quarterly by the "
    "internal auditing team."
]

# (label, answer, score a working judge should give, whether it should fail)
CASES = [
    ("faithful", "API prediction logs are retained for 90 days.", "~1.0", False),
    ("fully fabricated", "API prediction logs are retained for 7 years and archived to tape in Iceland.", "~0.0", True),
    ("half fabricated", "API prediction logs are retained for 90 days and encrypted with AES-512.", "~0.5", True),
    ("wrong figure", "API prediction logs are retained for 30 days.", "~0.0", True),
]


def main() -> int:
    data = {
        "question": ["How long are API prediction logs retained?"] * len(CASES),
        "answer": [c[1] for c in CASES],
        "contexts": [CONTEXT] * len(CASES),
        "ground_truth": ["90 days."] * len(CASES),
        "reference": ["90 days."] * len(CASES),
    }
    judge = LangchainLLMWrapper(ChatGroq(model=JUDGE_MODEL, temperature=0, timeout=90, max_retries=5))
    result = evaluate(Dataset.from_dict(data), metrics=[faithfulness], llm=judge,
                      raise_exceptions=False, run_config=RunConfig(max_workers=1, timeout=180))
    scores = result.to_pandas()["faithfulness"].tolist()

    print(f"Judge: {JUDGE_MODEL}\n")
    print(f"{'case':18} {'expect':>7} {'got':>6}  answer")
    rubber_stamped = []
    for (label, answer, expect, should_fail), got in zip(CASES, scores, strict=True):
        shown = "  n/a" if got != got else f"{got:6.2f}"
        print(f"{label:18} {expect:>7} {shown}  {answer}")
        if should_fail and got == got and got >= 0.99:
            rubber_stamped.append(label)

    if rubber_stamped:
        print(f"\nFAIL: the judge scored {rubber_stamped} as fully faithful. "
              "Its faithfulness scores cannot be trusted.")
        return 1
    print("\nPASS: the judge catches fabrication, so a 1.0 from it is a real 1.0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
