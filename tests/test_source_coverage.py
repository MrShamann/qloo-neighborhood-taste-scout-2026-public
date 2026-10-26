"""Original authored Qloo mock source-coverage falsification.

This measures only ID-level explanation availability, NOT real Qloo model
accuracy, human taste, group harmony, business value or prize likelihood.
"""
import copy
import json
import unittest

from src.taste_bridge import bridge_catalogue, offline_bridge, _normalize_places


class SourceCoverageTests(unittest.TestCase):
    def test_each_fictional_scene_discloses_two_one_and_zero_source_ids(self):
        for scene in bridge_catalogue():
            with self.subTest(scene=scene["id"]):
                result=offline_bridge(scene["id"])
                places=result["places"]
                self.assertEqual(len(places),3)
                self.assertEqual(
                    [p["source_coverage_count"] for p in places],
                    [2,1,0]
                )
                self.assertEqual(
                    [p["source_coverage_state"] for p in places],
                    [
                        "BOTH_EXPLICIT_INPUT_IDS",
                        "ONE_EXPLICIT_INPUT_ID",
                        "NO_INTEREST_ATTRIBUTION_PROVIDED",
                    ],
                )
                self.assertTrue(all(p["source_coverage_is_user_fit"] is False for p in places))
                self.assertEqual(
                    [p["agent_decision"] for p in places], [
                        "SOURCE_VALUES_FOR_BOTH_REVIEW_ONLY",
                        "SECOND_INTEREST_NOT_EVIDENCED",
                        "ABSTAIN_NO_INTEREST_ATTRIBUTION",
                    ])
                self.assertTrue(all(
                    p["agent_decision_is_automatic_approval"] is False for p in places))
                self.assertEqual(result["provider_api_calls"],0)
                self.assertFalse(result["provider_verified"])

    def test_unknown_or_duplicate_artist_id_never_counts_as_second_supported_input(self):
        from src.taste_bridge import _private_bridge,resolve_artist
        scene=_private_bridge("bridge-new-york")
        ids=[resolve_artist(row,name) for row,name in
             zip(scene["replay"]["searches"],scene["artists"])]
        original=scene["replay"]["insights"]
        first=original["results"]["entities"][0]
        mutated=copy.deepcopy(original)
        refs=mutated["results"]["entities"][0]["query"]["explainability"]["signal.interests.entities"]
        refs[1]["entity_id"]="11111111-1111-1111-1111-111111111111"
        rows=_normalize_places(mutated,ids,3,True)
        self.assertEqual(rows[0]["source_coverage_count"],1)
        self.assertEqual(rows[0]["source_coverage_state"],"ONE_EXPLICIT_INPUT_ID")
        mutated=copy.deepcopy(original)
        refs=mutated["results"]["entities"][0]["query"]["explainability"]["signal.interests.entities"]
        refs[1]["entity_id"]=refs[0]["entity_id"]
        rows=_normalize_places(mutated,ids,3,True)
        self.assertEqual(rows[0]["source_coverage_count"],1)
        self.assertEqual(len(rows[0]["source_explainability"]),1)
        self.assertFalse(rows[0]["source_coverage_is_user_fit"])

    def test_unusable_score_cannot_claim_evidence_of_both_interests(self):
        from src.taste_bridge import _private_bridge,resolve_artist
        scene=_private_bridge("bridge-tokyo")
        ids=[resolve_artist(row,name) for row,name in
             zip(scene["replay"]["searches"],scene["artists"])]
        mutated=copy.deepcopy(scene["replay"]["insights"])
        refs=mutated["results"]["entities"][0]["query"]["explainability"]["signal.interests.entities"]
        refs[1]["score"]=float("nan")
        rows=_normalize_places(mutated,ids,3,True)
        self.assertEqual(rows[0]["source_coverage_count"],1)
        self.assertFalse(rows[0]["source_coverage_is_user_fit"])


    def test_zero_and_subprecision_scores_never_create_second_evidence(self):
        from src.taste_bridge import _private_bridge, resolve_artist
        scene = _private_bridge("bridge-new-york")
        ids = [resolve_artist(x, name) for x, name in
               zip(scene["replay"]["searches"], scene["artists"])]
        for value in (0, -0.001, 0.00001, float("nan"), float("inf")):
            with self.subTest(value=value):
                altered = copy.deepcopy(scene["replay"]["insights"])
                entries = altered["results"]["entities"][0]["query"]["explainability"]["signal.interests.entities"]
                entries[1]["score"] = value
                result = _normalize_places(altered, ids, 3, True)
                self.assertEqual(result[0]["source_coverage_count"], 1)
                self.assertEqual(result[0]["agent_decision"],
                                 "SECOND_INTEREST_NOT_EVIDENCED")



if __name__=="__main__":
    unittest.main()
