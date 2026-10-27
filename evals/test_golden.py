"""
Integrity tests for evals/golden_set.json.   python -m unittest discover -s evals

A malformed golden set produces confident wrong numbers rather than an error.
Two categories once generated the same question ids, and the report paired
"Who won the 2022 World Cup?" with the answer to a question about Slack. These
pin the properties the harness relies on.
"""

import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "pcaps")
KNOWN_CATEGORIES = {
    "single_fact", "distractor", "multi_hop", "paraphrase", "injection",
    "unanswerable_in_domain", "unanswerable_out_of_domain",
}

with open(os.path.join(HERE, "golden_set.json"), encoding="utf-8") as fh:
    GOLDEN = json.load(fh)


class GoldenSetTests(unittest.TestCase):

    def test_ids_are_unique(self):
        ids = [q["id"] for q in GOLDEN]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(duplicates, [], "answers are cached by id, so duplicates get mixed up")

    def test_questions_are_unique(self):
        questions = [q["question"] for q in GOLDEN]
        self.assertEqual(len(questions), len(set(questions)))

    def test_every_category_is_known(self):
        self.assertEqual({q["category"] for q in GOLDEN} - KNOWN_CATEGORIES, set())

    def test_answerable_flag_matches_the_category(self):
        for q in GOLDEN:
            with self.subTest(id=q["id"]):
                self.assertEqual(q["answerable"], not q["category"].startswith("unanswerable"))

    def test_answerable_questions_can_be_scored_without_an_llm(self):
        for q in GOLDEN:
            if q["answerable"]:
                with self.subTest(id=q["id"]):
                    self.assertTrue(q.get("key_facts"), "needs key_facts for correctness")
                    self.assertTrue(all(group for group in q["key_facts"]), "empty key-fact group")
                    self.assertTrue(q.get("relevant_sources"), "needs relevant_sources for retrieval")

    def test_relevant_sources_exist_in_the_corpus(self):
        corpus = set(os.listdir(CORPUS))
        for q in GOLDEN:
            for source in q.get("relevant_sources") or []:
                with self.subTest(id=q["id"], source=source):
                    self.assertIn(source, corpus)

    def test_the_suite_has_enough_negatives_to_mean_something(self):
        """Two unanswerable questions is how the first threshold got miscalibrated."""
        self.assertGreaterEqual(sum(not q["answerable"] for q in GOLDEN), 15)


if __name__ == "__main__":
    unittest.main()
