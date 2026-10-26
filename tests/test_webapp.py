import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from src.webapp import CSP, DemoHandler, catalogue, scene_request, select_scene
from src.taste_scout import GuardError


class ProductUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),DemoHandler)
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(4)

    def call(self,method,path,data=None,headers=None):
        req=urllib.request.Request(self.url+path,method=method,data=data,headers=headers or {})
        try:
            with urllib.request.urlopen(req,timeout=5) as x:
                return x.status,x.headers,x.read()
        except urllib.error.HTTPError as e:
            try:return e.code,e.headers,e.read()
            finally:e.close()

    def body(self,mode="mock",id="jazz-new-york"):
        return json.dumps({"scene_id":id,"mode":mode}).encode()

    def test_chatgpt_tracking_query_does_not_break_static_demo(self):
        for url in ("/?utm_source=chatgpt.com",
                    "/styles.css?utm_source=chatgpt.com",
                    "/app.js?utm_source=chatgpt.com"):
            with self.subTest(url=url):
                code,headers,body=self.call("GET",url)
                self.assertEqual(code,200)
                self.assertTrue(len(body)>100)
                self.assertEqual(headers.get("Cache-Control"),"no-store")

    def test_api_query_parameters_fail_closed(self):
        code,headers,body=self.call("GET","/api/scenes?utm_source=chatgpt.com")
        self.assertEqual(code,400)
        self.assertEqual(json.loads(body)["error"],"API_QUERY_NOT_ALLOWED")

    def test_unknown_tracking_route_still_not_found(self):
        code,headers,body=self.call("GET","/not-a-route?utm_source=chatgpt.com")
        self.assertEqual(code,404)

    def test_tracking_query_does_not_bypass_host_validation(self):
        code,headers,body=self.call("GET","/?utm_source=chatgpt.com",
                                    headers={"Host":"untrusted.example"})
        self.assertEqual(code,403)

    def test_bridge_catalogue_is_public_metadata_only(self):
        status,headers,raw=self.call("GET","/api/bridges")
        self.assertEqual(status,200)
        body=json.loads(raw)
        self.assertEqual(len(body["bridges"]),3)
        self.assertFalse(body["provider_ready"])
        self.assertFalse(body["event_key_exposed"])
        self.assertTrue(all("replay" not in row for row in body["bridges"]))

    def test_bridge_all_fictional_scenarios_end_to_end(self):
        from src.taste_bridge import bridge_catalogue
        for scene in bridge_catalogue():
            with self.subTest(scene=scene["id"]):
                request=json.dumps({"bridge_id":scene["id"],"mode":"mock"}).encode()
                status,headers,raw=self.call("POST","/api/bridge",
                     request,{"Content-Type":"application/json",
                              "Origin":self.url})
                result=json.loads(raw)
                self.assertEqual(status,200,result)
                self.assertEqual(result["mode"],"SYNTHETIC_BRIDGE_REPLAY_NO_API")
                self.assertFalse(result["provider_verified"])
                self.assertEqual(result["provider_api_calls"],0)
                self.assertEqual(result["automatic_actions"],0)
                self.assertEqual(len(result["artists"]),2)
                self.assertEqual(len(result["places"]),3)
                self.assertTrue(result["human_confirmation_required"])

    def test_bridge_real_mode_fails_without_key_or_quota(self):
        request=json.dumps({"bridge_id":"bridge-new-york","mode":"live"}).encode()
        with patch.dict(os.environ,{"QLOO_API_KEY":"",
                  "QLOO_EVENT_QUOTA_APPROVED":"NO"}):
            status,headers,raw=self.call("POST","/api/bridge",
                 request,{"Content-Type":"application/json",
                          "Origin":self.url})
        self.assertEqual(status,422)
        self.assertEqual(json.loads(raw)["error"],"VALIDATION_OR_PROVIDER_GATE_BLOCKED")

    def test_bridge_illegal_origin_cannot_invoke_calls(self):
        request=json.dumps({"bridge_id":"bridge-new-york","mode":"mock"}).encode()
        status,_,raw=self.call("POST","/api/bridge",
             request,{"Content-Type":"application/json",
                      "Origin":"https://malicious.example"})
        self.assertEqual(status,403)

    def test_bridge_rejects_extra_fields_without_key_exposure(self):
        variants=[
            {"bridge_id":"bridge-new-york","mode":"mock","email":"a@example.test"},
            {"bridge_id":"bridge-new-york","mode":"pay"},
            {"bridge_id":"bridge-fake","mode":"mock"},
            {"bridge_id":42,"mode":"mock"},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                status,_,raw=self.call("POST","/api/bridge",
                    json.dumps(variant).encode(),
                    {"Content-Type":"application/json"})
                self.assertEqual(status,422)
                self.assertNotIn(b"QLOO_API_KEY",raw)

    def test_bridge_api_query_parameters_are_rejected(self):
        status,_,raw=self.call("GET","/api/bridges?utm_source=chatgpt.com")
        self.assertEqual(status,400)
        status,_,raw=self.call("POST","/api/bridge?utm_source=chatgpt.com",
           b"{}",{"Content-Type":"application/json"})
        self.assertEqual(status,404)

    def test_bridge_frontend_wiring_is_visible_and_truth_labeled(self):
        status,_,raw=self.call("GET","/")
        self.assertEqual(status,200)
        self.assertIn(b'id="bridge-workshop"',raw)
        self.assertIn(b'id="bridge-live"',raw)
        self.assertIn(b'id="bridge-decision-note"',raw)
        self.assertIn(b"FICTIONAL",raw)
        status,_,js=self.call("GET","/app.js")
        self.assertEqual(status,200)
        self.assertIn(b"/api/bridges",js)
        self.assertIn(b"/api/bridge",js)
        self.assertIn(b"SYNTHETIC_BRIDGE_REPLAY_NO_API",js)

    def test_index_is_self_hosted_and_csp(self):
        status,h,b=self.call("GET","/")
        self.assertEqual(status,200)
        self.assertEqual(h.get("Content-Security-Policy"),CSP)
        self.assertEqual(h.get("Cache-Control"),"no-store")
        self.assertIn(b"Neighborhood Taste Scout",b)

    def test_static_scripts_have_no_external_keys(self):
        for path in ("/app.js","/styles.css"):
            code,h,b=self.call("GET",path)
            self.assertEqual(code,200)
            self.assertNotIn(b"QLOO_API_KEY",b)
            self.assertNotIn(b"https://",b)

    def test_catalogue_never_returns_replay_raw(self):
        code,h,b=self.call("GET","/api/scenes")
        data=json.loads(b)
        self.assertEqual(code,200)
        self.assertEqual(len(data["scenes"]),3)
        self.assertFalse(data["provider_ready"])
        self.assertTrue(all("replay" not in s for s in data["scenes"]))

    def test_mock_end_to_end_all_predefined_scenes(self):
        for scene in catalogue():
            with self.subTest(scene=scene["id"]):
                code,headers,body=self.call("POST","/api/execute",self.body(id=scene["id"]),
                    {"Content-Type":"application/json"})
                v=json.loads(body)
                self.assertEqual(code,200,v)
                self.assertFalse(v["provider_verified"])
                self.assertEqual(v["mode"],"SYNTHETIC_FIXTURE_NO_API_CALL")
                self.assertEqual(v["brief"]["city"],scene["city"])
                self.assertEqual(len(v["places"]),3)
                self.assertTrue(all(x["name"].startswith("Fictional") for x in v["places"]))
                self.assertTrue(v["human_confirmation_required"])

    def test_unsafe_live_call_blocked_without_key(self):
        with patch.dict(os.environ,{"QLOO_API_KEY":"","QLOO_EVENT_QUOTA_APPROVED":"NO"}):
            code,headers,b=self.call("POST","/api/execute",self.body(mode="live"),
                                       {"Content-Type":"application/json"})
        self.assertEqual(code,422)
        self.assertEqual(json.loads(b)["error"],"VALIDATION_OR_PROVIDER_GATE_BLOCKED")

    def test_foreign_origin_denied(self):
        code,h,b=self.call("POST","/api/execute",self.body(),
                {"Content-Type":"application/json","Origin":"https://adversary.example"})
        self.assertEqual(code,403)

    def test_wrong_format_denied(self):
        code,h,b=self.call("POST","/api/execute",self.body(),
                           {"Content-Type":"application/x-www-form-urlencoded"})
        self.assertEqual(code,415)

    def test_extra_fields_denied(self):
        bad=json.dumps({"scene_id":"jazz-new-york","mode":"mock","email":"test@example.test"}).encode()
        code,h,b=self.call("POST","/api/execute",bad,{"Content-Type":"application/json"})
        self.assertEqual(code,422)

    def test_unknown_scenes_denied(self):
        for x in ("../../etc/passwd",42,{},None,[], "jazz-london"):
            with self.subTest(scene=x):
                code,h,b=self.call("POST","/api/execute",self.body(id=x),
                      {"Content-Type":"application/json"})
                self.assertEqual(code,422)

    def test_oversized_body_denied(self):
        code,h,b=self.call("POST","/api/execute",b"X"*1024,
                    {"Content-Type":"application/json"})
        self.assertEqual(code,413)

    def test_dns_rebinding_host_header_denied(self):
        for method,body,headers in (
            ("GET",None,{"Host":"other.example:8879"}),
            ("POST",self.body(),{"Host":"other.example:8879","Content-Type":"application/json"})):
            with self.subTest(method=method):
                code,h,data=self.call(method,"/api/execute" if method=="POST" else "/api/scenes",
                                        body,headers)
                self.assertEqual(code,403)
                self.assertEqual(json.loads(data)["error"],"INVALID_LOOPBACK_HOST")

    def test_path_traversal_denied(self):
        code,h,b=self.call("GET","/../../.git/config")
        self.assertEqual(code,404)

    def test_cors_preflight_denied(self):
        code,h,b=self.call("OPTIONS","/api/execute")
        self.assertEqual(code,405)

    def test_scene_adapter_only_fixed_synthetic(self):
        for scene in catalogue():
            self.assertEqual(scene_request(select_scene(scene["id"]))["mode"],"synthetic_group")


if __name__=="__main__":
    unittest.main()
