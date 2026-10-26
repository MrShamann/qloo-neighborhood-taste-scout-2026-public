"""Independent adversarial regression against official 2026 Qloo API contracts."""
import json
import os
import urllib.error
import urllib.parse
import unittest
from unittest.mock import patch
from src.taste_scout import (
    GuardError, fixture, insights_url, live_flow, offline_flow,
    read_insights, resolve_artist, search_url, valid_input
)

ID_1="4B5FA5D2-5CC6-42B0-9102-FA0000000001"
ID_2="4B5FA5D2-5CC6-42B0-9102-FA0000000002"


class OfficialContractTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture()

    def test_search_uses_documented_types_plural(self):
        query=urllib.parse.parse_qs(urllib.parse.urlsplit(search_url(self.case)).query)
        self.assertEqual(query.get("types"),["urn:entity:artist"])
        self.assertNotIn("type",query)
        self.assertEqual(query.get("take"),["3"])

    def test_geographic_location_strict_and_explainability(self):
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(insights_url(self.case,ID_1)).query)
        self.assertEqual(q["filter.location.radius"],["0"])
        self.assertEqual(q["feature.explainability"],["true"])
        self.assertEqual(q["filter.type"],["urn:entity:place"])

    def test_nonstring_city_lists_rejected(self):
        for x in ([],{},None,1):
            with self.subTest(x=x),self.assertRaises(GuardError):
                valid_input(dict(self.case,city=x))

    def test_malformed_uuid_rejected(self):
        for x in ("not-a-qloo-id","z"*36,["4B5FA5D2"],"4B5FA5D2-5CC6-42B0-9102-FA00000000011"):
            with self.subTest(id=x),self.assertRaises(GuardError):
                resolve_artist({"results":[{"name":"Miles Davis","id":x,
                                         "types":["urn:entity:artist"]}]},"Miles Davis")

    def test_search_type_mismatch_not_silently_selected(self):
        with self.assertRaises(GuardError):
            resolve_artist({"results":[{"name":"Miles Davis","id":ID_1,
                                        "types":["urn:entity:place"]}]},"Miles Davis")

    def test_search_explicit_failure(self):
        with self.assertRaises(GuardError):
            resolve_artist({"success":False,"results":[{"name":"Miles Davis","id":ID_1}]},"Miles Davis")

    def test_insights_explicit_failure(self):
        with self.assertRaises(GuardError):
            read_insights({"success":False,"results":{"entities":[]}},3)

    def test_dedupe_ids_and_no_fake_scores(self):
        records={"results":{"entities":[{"name":"Place A","entity_id":ID_1},
                                          {"name":"Place A duplicate","entity_id":ID_1},
                                          {"name":"Place B","entity_id":ID_2}]}}
        result=read_insights(records,3)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]["rank"],1)
        self.assertEqual(result[1]["rank"],2)
        self.assertNotIn("score",result[0])

    def test_offline_plan_has_mock_truth_everywhere(self):
        r=offline_flow(self.case)
        self.assertFalse(r["provider_verified"])
        self.assertEqual([x["status"] for x in r["agent_steps"]][:2],["MOCK","MOCK"])
        self.assertEqual(r["limits"][0],"All place names are fictional fixtures.")

    def test_fail_closed_network_without_key_leak(self):
        def fail(req,timeout):
            raise urllib.error.URLError("network unavailable")
        with patch.dict(os.environ,{"QLOO_API_KEY":"sentinel_fake_secret_no_leak",
                                    "QLOO_EVENT_QUOTA_APPROVED":"YES"}):
            with self.assertRaises(GuardError) as e:
                live_flow(self.case,fetcher=fail)
        self.assertNotIn("sentinel_fake_secret_no_leak",str(e.exception))

    def test_unsupported_live_input_denied_before_key(self):
        bad=dict(self.case,mode="individual")
        with patch.dict(os.environ,{"QLOO_API_KEY":"", "QLOO_EVENT_QUOTA_APPROVED":"NO"}):
            with self.assertRaises(GuardError):
                live_flow(bad,fetcher=lambda *args,**kw:self.fail("no network"))

    def test_fully_unverified_offline_works_without_vendor_access(self):
        with patch.dict(os.environ,{"QLOO_API_KEY":"","QLOO_EVENT_QUOTA_APPROVED":"NO"}):
            result=offline_flow(self.case)
        self.assertEqual(result["mode"],"SYNTHETIC_FIXTURE_NO_API_CALL")


if __name__=="__main__":
    unittest.main()
