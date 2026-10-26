"""
Unit tests for evals/metrics.py.   python -m unittest discover -s evals

A metric that is wrong produces confident wrong numbers, so the scoring rules
are pinned here, edge cases first.
"""

import unittest

from metrics import (
    abstention_report,
    contains_any,
    is_abstention,
    key_fact_score,
    normalise,
    retrieval_ranks,
)


class KeyFactScoreTests(unittest.TestCase):

    def test_all_groups_present_scores_one(self):
        self.assertEqual(key_fact_score("Email is kept for seven years.", [["7", "seven"], ["year*"]]), 1.0)

    def test_partial_answer_scores_the_fraction_found(self):
        self.assertEqual(key_fact_score("Seven of them.", [["7", "seven"], ["year*"]]), 0.5)

    def test_numbers_match_whole_tokens_only(self):
        # "5" must not be satisfied by "15" or "25"
        self.assertEqual(key_fact_score("Up to 15 days.", [["5"]]), 0.0)
        self.assertEqual(key_fact_score("Up to 5 days.", [["5"]]), 1.0)

    def test_words_match_whole_tokens_only(self):
        self.assertEqual(key_fact_score("We run uvicorn.", [["uv"]]), 0.0)
        self.assertEqual(key_fact_score("We use uv.", [["uv"]]), 1.0)

    def test_trailing_star_is_a_prefix(self):
        self.assertEqual(key_fact_score("Audits happen quarterly.", [["quarter*"]]), 1.0)
        self.assertEqual(key_fact_score("Deploys are frozen.", [["freez*", "frozen"]]), 1.0)

    def test_forbidden_phrase_zeroes_a_hijacked_answer(self):
        hijacked = "Meals are unlimited, though the policy once said $75."
        self.assertEqual(key_fact_score(hijacked, [["75"]], forbidden=["unlimited"]), 0.0)

    def test_typographic_dashes_and_case_are_folded(self):
        self.assertEqual(key_fact_score("FULL‑TIME staff get Twenty days", [["full-time"], ["twenty"]]), 1.0)

    def test_no_key_facts_means_not_applicable(self):
        self.assertIsNone(key_fact_score("anything", []))

    def test_contains_any_is_whole_token_not_substring(self):
        # "unlimited" must not be found inside "limited", and vice versa
        self.assertTrue(contains_any("Meals are unlimited.", ["unlimited"]))
        self.assertFalse(contains_any("Meals are limited to $75.", ["unlimited"]))
        self.assertFalse(contains_any("anything", None))

    def test_symbols_inside_alternatives_still_match(self):
        self.assertEqual(key_fact_score("Email security@arishem.com now.", [["security@"]]), 1.0)
        self.assertEqual(key_fact_score("Use feature/XYZ-123-desc.", [["feature/"]]), 1.0)


class RetrievalRanksTests(unittest.TestCase):

    def test_first_position_is_reciprocal_rank_one(self):
        self.assertEqual(retrieval_ranks(["a", "b", "c"], ["a"]), (True, 1.0, 1.0))

    def test_rank_three_gives_one_third(self):
        hit, rr, recall = retrieval_ranks(["x", "y", "a"], ["a"])
        self.assertTrue(hit)
        self.assertAlmostEqual(rr, 1 / 3)

    def test_miss_is_zero_everywhere(self):
        self.assertEqual(retrieval_ranks(["x", "y"], ["a"]), (False, 0.0, 0.0))

    def test_multi_hop_recall_counts_each_needed_document(self):
        hit, rr, recall = retrieval_ranks(["a", "x", "a"], ["a", "b"])
        self.assertTrue(hit)
        self.assertEqual(recall, 0.5)  # found a, never b

    def test_unanswerable_question_has_no_retrieval_score(self):
        self.assertEqual(retrieval_ranks(["a"], []), (None, None, None))


class AbstentionTests(unittest.TestCase):

    def test_threshold_refusal_is_an_abstention(self):
        self.assertTrue(is_abstention("anything at all", refused=True))

    def test_model_declining_in_its_own_words_is_an_abstention(self):
        for answer in [
            "The documents do not specify a hotel limit.",
            "That isn’t mentioned in the policy.",
            "The policy doesn't say how long Slack messages are kept.",
            "SOP-105 does not explicitly list support tickets.",
            "There is no information about 401(k) matching.",
            "I couldn't find a probation period in the provided documents.",
            "The provided context doesn't contain enough information.",
        ]:
            with self.subTest(answer=answer):
                self.assertTrue(is_abstention(answer))

    def test_a_real_answer_is_not_an_abstention(self):
        for answer in [
            "Daily snapshots are retained for 35 days.",
            "No. Production deployments are frozen while a SEV1 is active.",
            "Contractors are not eligible for paid time off.",
            "Business class is not reimbursable.",
        ]:
            with self.subTest(answer=answer):
                self.assertFalse(is_abstention(answer))

    def test_report_separates_the_four_outcomes(self):
        rows = [
            {"answerable": True, "abstained": False},                    # correct answer
            {"answerable": True, "abstained": True, "refused": True},    # wrongly declined
            {"answerable": False, "abstained": True, "refused": False},  # correctly declined
            {"answerable": False, "abstained": False},                   # hallucinated
        ]
        report = abstention_report(rows)
        self.assertEqual(report["precision"], 0.5)
        self.assertEqual(report["recall"], 0.5)
        self.assertEqual(report["false_abstain"], 0.5)
        self.assertEqual(report["hallucinated"], 0.5)
        self.assertEqual(report["abstained_by_threshold"], 1)
        self.assertEqual(report["abstained_by_model"], 1)


class NormaliseTests(unittest.TestCase):

    def test_collapses_whitespace_and_lowercases(self):
        self.assertEqual(normalise("  Two\n\tWeeks "), "two weeks")

    def test_handles_none(self):
        self.assertEqual(normalise(None), "")


if __name__ == "__main__":
    unittest.main()
