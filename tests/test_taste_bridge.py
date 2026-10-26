"""Independent source-aware acceptance and falsification for a dual-taste Qloo agent."""
import json
import os
import urllib.parse
import unittest
from unittest.mock import patch

from src.taste_bridge import (
    BRIDGE_TRUTH, LIVE_TRUTH, _normalize_places, bridge_catalogue,
    bridge_insights_url, live_bridge, offline_bridge,
)
from src.taste_scout import HOST, GuardError

ONE="7E4CA610-27AB-4823-9D91-BB0000000101"
TWO="7E4CA610-27AB-4823-9D91-BB0000000102"
VENUE="7E4CA610-27AB-4823-9D91-BB0000000111"

class Response:
    def __init__(self,body,status=200):
        self.status=status
        self.raw=json.dumps(body).encode()
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,n):
        return self.raw[:n]

class TasteBridgeTests(unittest.TestCase):
    def test_three_curated_group_scenarios_do_not_export_fake_sources(self):
        rows=bridge_catalogue()
        self.assertEqual(len(rows),3)
        self.assertTrue(all(len(row["artists"])==2 for row in rows))
        self.assertTrue(all("replay" not in row for row in rows))
        self.assertTrue(all("@" not in row["objective"] for row in rows))

    def test_every_offline_bridge_has_only_fake_provider_truth(self):
        for row in bridge_catalogue():
            with self.subTest(scene=row["id"]):
                result=offline_bridge(row["id"])
                self.assertEqual(result["mode"],BRIDGE_TRUTH)
                self.assertFalse(result["provider_verified"])
                self.assertEqual(result["provider_api_calls"],0)
                self.assertEqual(result["automatic_actions"],0)
                self.assertTrue(result["human_confirmation_required"])
                self.assertEqual(len(result["artists"]),2)
                self.assertEqual(len(result["places"]),3)
                self.assertTrue(all(x["name"].startswith("Fictional ")
                                    for x in result["places"]))
                self.assertFalse(result["comparison"]["measured_user_benefit_proven"])

    def test_two_artist_signals_are_sent_as_comma_separated_uuid_ids(self):
        url=bridge_insights_url("New York",[ONE,TWO])
        self.assertTrue(url.startswith(HOST+"/v2/insights?"))
        p=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(p["signal.interests.entities"],[ONE+","+TWO])
        self.assertEqual(p["feature.explainability"],["true"])
        self.assertEqual(p["filter.type"],["urn:entity:place"])
        self.assertEqual(p["filter.location.query"],["New York"])
        self.assertEqual(p["filter.location.radius"],["0"])
        self.assertEqual(p["take"],["3"])
        self.assertNotIn("email",url.casefold())
        self.assertNotIn("api_key",url.casefold())

    def test_second_artist_changes_exact_grounding_request(self):
        third="7E4CA610-27AB-4823-9D91-BB0000000103"
        one=bridge_insights_url("New York",[ONE,TWO])
        other=bridge_insights_url("New York",[ONE,third])
        self.assertNotEqual(one,other)
        self.assertIn(third,urllib.parse.unquote(other))
        self.assertNotIn(TWO,other)
        # This proves request sensitivity, NOT measured taste lift.
        self.assertFalse(offline_bridge("bridge-new-york")[
            "comparison"]["cross_taste_lift_proven"])

    def test_unknown_or_duplicate_artist_ids_fail(self):
        for ids in ([ONE,ONE],["short",TWO],[ONE],["",TWO]):
            with self.subTest(ids=ids),self.assertRaises(GuardError):
                bridge_insights_url("Tokyo",ids)

    def test_unrecognized_and_malicious_scene_ids_fail_closed(self):
        for bad in ("../../.env","",None,True,"bridge-fantasy","a"*60):
            with self.subTest(handle=bad),self.assertRaises(GuardError):
                offline_bridge(bad)

    def test_mock_explainability_is_explicit_and_not_guessed(self):
        r=offline_bridge("bridge-new-york")
        self.assertEqual(r["source_explainability_count"],2)
        self.assertEqual(len(r["places"][0]["source_explainability"]),2)
        self.assertEqual(len(r["places"][1]["source_explainability"]),1)
        self.assertEqual(r["places"][2]["source_attribution_state"],
                         "UNAVAILABLE_NOT_INFERRED")

    def test_missing_explainability_yields_zero_attribution(self):
        data={"results":{"entities":[{"name":"Test Venue","entity_id":VENUE,
            "type":"urn:entity","subtype":"urn:entity:place"}]}}
        p=_normalize_places(data,[ONE,TWO],3,False)
        self.assertEqual(p[0]["source_explainability"],[])
        self.assertEqual(p[0]["source_attribution_state"],"UNAVAILABLE_NOT_INFERRED")

    def test_official_qloo_type_and_subtype_are_accepted_without_laundering(self):
        # Official Qloo basic-insights sample uses type=urn:entity and
        # subtype=urn:entity:<category>, NOT type=urn:entity:place.
        docs_shape={"name":"Official-schema Test Venue","entity_id":VENUE,
                    "type":"urn:entity","subtype":"urn:entity:place",
                    "query":{"explainability":{"signal.interests.entities":[
                       {"entity_id":ONE,"score":0.4},
                       {"entity_id":TWO,"score":0.3}]}}}
        places=_normalize_places({"success":True,
                                  "results":{"entities":[docs_shape]}},
                                 [ONE,TWO],3,False)
        self.assertEqual(len(places),1)
        self.assertEqual(places[0]["source_coverage_count"],2)
        self.assertEqual(places[0]["agent_decision"],
                         "SOURCE_VALUES_FOR_BOTH_REVIEW_ONLY")
        self.assertFalse(places[0]["agent_decision_is_automatic_approval"])

    def test_generic_untyped_and_conflicting_subtype_are_not_assumed_places(self):
        wrong=[
            {"name":"Generic untyped item","entity_id":VENUE},
            {"name":"Only generic entity category","entity_id":VENUE,
             "type":"urn:entity"},
            {"name":"Artist subtype under generic entity","entity_id":VENUE,
             "type":"urn:entity","subtype":"urn:entity:artist"},
            {"name":"Conflicting place and artist subtype","entity_id":VENUE,
             "type":"urn:entity:place","subtype":"urn:entity:artist"},
        ]
        with self.assertRaises(GuardError):
            _normalize_places({"results":{"entities":wrong}},[ONE,TWO],3,False)

    def test_wrong_source_category_is_not_mislabeled_as_place(self):
        wrong=[
            {"name":"An artist, not a venue","entity_id":ONE,
             "type":"urn:entity:artist"},
            {"name":"A brand, not a venue","entity_id":TWO,
             "types":["urn:entity:brand"]},
            {"name":"Contradictory type fields","entity_id":ONE,
             "type":"urn:entity:place","types":["urn:entity:artist"]},
        ]
        correct={"name":"Source Venue","entity_id":VENUE,
                 "types":["urn:entity:place"]}
        results=_normalize_places(
            {"results":{"entities":[*wrong,correct]}},[ONE,TWO],3,False)
        self.assertEqual([r["name"] for r in results],["Source Venue"])
        with self.assertRaises(GuardError):
            _normalize_places(
                {"results":{"entities":wrong}},[ONE,TWO],3,False)

    def test_invented_explainability_inputs_are_not_accepted(self):
        input_body={"results":{"entities":[{
            "name":"Test Source Venue","entity_id":VENUE,
            "type":"urn:entity","subtype":"urn:entity:place","query":{
              "explainability":{"signal.interests.entities":[
                {"entity_id":"7E4CA610-27AB-4823-9D91-FA0000000000","score":0.98},
                {"entity_id":ONE,"score":1.9},
                {"entity_id":TWO,"score":True},
                {"entity_id":ONE,"score":0.35},
              ]}}
        }]}}
        p=_normalize_places(input_body,[ONE,TWO],3,False)
        self.assertEqual(p[0]["source_explainability"],[
                         {"entity_id":ONE,"score":0.35}])
        self.assertNotIn("FA0000000000",str(p))

    def test_unlabeled_real_venue_cannot_enter_fake_replay(self):
        with self.assertRaises(GuardError):
            _normalize_places({"results":{"entities":[{
                "name":"Actual-looking Venue","entity_id":VENUE}]}},
                [ONE,TWO],3,True)

    def test_live_missing_key_cannot_open_socket(self):
        with patch.dict(os.environ,{"QLOO_API_KEY":"",
                   "QLOO_EVENT_QUOTA_APPROVED":"NO"}):
            with self.assertRaises(GuardError):
                live_bridge("bridge-new-york",fetcher=lambda *args,**kw:
                    self.fail("no network allowed"))

    def test_live_key_but_unverified_quota_is_still_blocked(self):
        with patch.dict(os.environ,{"QLOO_API_KEY":"fictional-test-token-only",
                   "QLOO_EVENT_QUOTA_APPROVED":"NO"}):
            with self.assertRaises(GuardError):
                live_bridge("bridge-new-york",fetcher=lambda *args,**kw:
                    self.fail("no network allowed"))

    def test_mocked_live_uses_two_searches_and_one_insights(self):
        calls=[]
        artist_records=[
            {"results":[{"name":"Miles Davis","entity_id":ONE,
                          "types":["urn:entity:artist"]}]},
            {"results":[{"name":"Radiohead","entity_id":TWO,
                          "types":["urn:entity:artist"]}]},
        ]
        result={"results":{"entities":[{
            "name":"Source-Returned Test Venue","entity_id":VENUE,
            "type":"urn:entity","subtype":"urn:entity:place",
            "query":{"explainability":{"signal.interests.entities":[
              {"entity_id":ONE,"score":0.56},
              {"entity_id":TWO,"score":0.23},
            ]}}
        }]}}
        def fake(req,timeout):
            calls.append(req)
            self.assertEqual(timeout,18)
            self.assertEqual(req.get_method(),"GET")
            self.assertTrue(req.full_url.startswith(HOST+"/"))
            self.assertEqual(req.get_header("X-api-key"),"fictional-test-token-only")
            return Response([*artist_records,result][len(calls)-1])
        with patch.dict(os.environ,{"QLOO_API_KEY":"fictional-test-token-only",
                   "QLOO_EVENT_QUOTA_APPROVED":"YES"}):
            record=live_bridge("bridge-new-york",fetcher=fake)
        self.assertEqual(len(calls),3)
        self.assertEqual(record["mode"],LIVE_TRUTH)
        self.assertTrue(record["provider_verified"])
        self.assertEqual(record["provider_api_calls"],3)
        self.assertEqual(record["source_explainability_count"],1)
        self.assertTrue(record["human_confirmation_required"])
        self.assertFalse(record["comparison"]["cross_taste_lift_proven"])
        self.assertEqual([urllib.parse.urlsplit(c.full_url).path for c in calls],
                         ["/search","/search","/v2/insights"])

    def test_ambiguous_first_entity_abstains_before_insights(self):
        calls=[]
        def fake(req,timeout):
            calls.append(req)
            return Response({"results":[{"name":"Miles Davis","entity_id":ONE,
                              "types":["urn:entity:artist"]},
                         {"name":"Miles Davis","entity_id":TWO,
                          "types":["urn:entity:artist"]}]})
        with patch.dict(os.environ,{"QLOO_API_KEY":"fictional-test-token-only",
                   "QLOO_EVENT_QUOTA_APPROVED":"YES"}),self.assertRaises(GuardError):
            live_bridge("bridge-new-york",fetcher=fake)
        self.assertEqual(len(calls),1)

    def test_source_failure_on_third_call_has_no_synthetic_fallback(self):
        calls=[]
        def fake(req,timeout):
            calls.append(req)
            if len(calls)==1:
                return Response({"results":[{"name":"Miles Davis","entity_id":ONE,
                              "types":["urn:entity:artist"]}]})
            if len(calls)==2:
                return Response({"results":[{"name":"Radiohead","entity_id":TWO,
                              "types":["urn:entity:artist"]}]})
            return Response({"results":{"entities":[]}})
        with patch.dict(os.environ,{"QLOO_API_KEY":"fictional-test-token-only",
                   "QLOO_EVENT_QUOTA_APPROVED":"YES"}),self.assertRaises(GuardError):
            live_bridge("bridge-new-york",fetcher=fake)
        self.assertEqual(len(calls),3)

    def test_http_not_200_abstains_without_retry(self):
        calls=[]
        def bad(req,timeout):
            calls.append(req)
            return Response({"error":"provider unavailable"},status=401)
        with patch.dict(os.environ,{"QLOO_API_KEY":"fictional-test-token-only",
                   "QLOO_EVENT_QUOTA_APPROVED":"YES"}),self.assertRaises(GuardError):
            live_bridge("bridge-new-york",fetcher=bad)
        self.assertEqual(len(calls),1)

if __name__=="__main__":
    unittest.main()
