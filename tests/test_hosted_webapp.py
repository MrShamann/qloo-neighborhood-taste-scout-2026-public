"""Independent hosted-ingress negative tests — no external service, no secrets."""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from src.hosted_webapp import HostedDemoHandler, hosted_server, validate_public_host

HOST = "scout.example.test"
ORIGIN = "https://" + HOST


class HostingConfigurationTest(unittest.TestCase):
    def test_valid_exact_public_host(self):
        self.assertEqual(validate_public_host("scout.example.test"), HOST)
        self.assertEqual(validate_public_host("demo.qloo-agent.example.com"),
                         "demo.qloo-agent.example.com")

    def test_deny_non_public_or_ambiguous_host(self):
        invalid = ("", "LOCALHOST", "localhost", "127.0.0.1",
                   "scout.localhost", "x.internal", "x.invalid",
                   "x.local", "X.Example.COM", "x.example.com:443",
                   "x.example.com/path", "user@x.example.com",
                   "-x.example.com", "x-.example.com",
                   "x..example.com", "x.example.com.",
                   "a"*64+".example.com", "éxample.com")
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_public_host(value)

    def test_public_interface_requires_both_approval_and_verified_free_host(self):
        with patch.dict(os.environ, {
                "QLOO_PUBLIC_DEPLOY_APPROVED":"NO",
                "QLOO_FREE_HOSTING_BILLING_VERIFIED":"NO"}):
            with self.assertRaises(ValueError):
                hosted_server(HOST, 18879, "0.0.0.0")
        with patch.dict(os.environ, {
                "QLOO_PUBLIC_DEPLOY_APPROVED":"YES",
                "QLOO_FREE_HOSTING_BILLING_VERIFIED":"NO"}):
            with self.assertRaises(ValueError):
                hosted_server(HOST, 18879, "0.0.0.0")
        with self.assertRaises(ValueError):
            hosted_server(HOST, 18879, "192.0.2.99")

    def test_invalid_ports_do_not_listen(self):
        for port in (0, 1023, 65536, True, "8879"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                hosted_server(HOST, port)


class HostedIngressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # ephemeral socket, never a public listener or paid external resource.
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), HostedDemoHandler)
        cls.server.public_hostname = HOST
        cls.server.daemon_threads = True
        cls.local_url = "http://127.0.0.1:" + str(cls.server.server_port)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=4)

    def request(self, method, path, payload=None, headers=None):
        req = urllib.request.Request(
            self.local_url + path, method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Host":HOST, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            try: return exc.code, dict(exc.headers), exc.read()
            finally: exc.close()

    def test_public_get_synthetic_case_catalogue_no_key(self):
        with patch.dict(os.environ, {"QLOO_API_KEY":"FAKE_SECRET_UNIT_TEST",
                 "QLOO_EVENT_QUOTA_APPROVED":"YES"}):
            status,headers,body = self.request("GET", "/api/bridges")
            data=json.loads(body)
            self.assertEqual(status,200)
            self.assertFalse(data["provider_ready"])
            self.assertFalse(data["event_key_exposed"])
            self.assertEqual(data["live_call_count"],0)
            self.assertEqual(len(data["bridges"]),3)
            self.assertNotIn(b"FAKE_SECRET",body)
            s,h,b=self.request("GET","/api/scenes")
            self.assertEqual(s,200)
            self.assertFalse(json.loads(b)["provider_ready"])
            self.assertEqual(json.loads(b)["live_call_count"],0)
            self.assertEqual(headers["Content-Security-Policy"].startswith("default-src 'none'"),True)

    def test_free_hosting_healthz_is_readonly_sponsor_free(self):
        with patch.dict(os.environ, {
                "QLOO_API_KEY":"UNIT_TEST_FAKE_CREDENTIAL",
                "QLOO_EVENT_QUOTA_APPROVED":"YES"}):
            status,headers,body = self.request("GET","/healthz")
        self.assertEqual(status,200)
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertEqual(json.loads(body),{
            "service":"qloo-taste-scout","status":"ready",
            "public_real_provider":False})
        self.assertNotIn(b"UNIT_TEST_FAKE_CREDENTIAL",body)
        for endpoint in ("/healthz?debug=1","/health",):
            with self.subTest(endpoint=endpoint):
                s,_,_ = self.request("GET",endpoint)
                self.assertNotEqual(s,200)
        s,_,v=self.request("GET","/healthz",headers={"Host":"evil.example"})
        self.assertEqual(s,403)
        self.assertEqual(json.loads(v)["error"],"INVALID_PUBLIC_HOST")

    def test_render_blueprint_is_offline_free_and_requires_manual_approval(self):
        from pathlib import Path
        yml=(Path(__file__).resolve().parents[1]/"render.yaml").read_text()
        self.assertIn("plan: free",yml)
        self.assertIn("autoDeployTrigger: off",yml)
        self.assertIn("healthCheckPath: /healthz",yml)
        self.assertIn("src.hosted_webapp",yml)
        self.assertIn("QLOO_PUBLIC_DEPLOY_APPROVED",yml)
        self.assertIn("QLOO_FREE_HOSTING_BILLING_VERIFIED",yml)
        self.assertNotIn("QLOO_API_KEY",yml)
        self.assertNotIn("QLOO_EVENT_QUOTA_APPROVED",yml)

    def test_browser_synthetic_post_exposes_no_real_api(self):
        status,headers,body=self.request("POST","/api/bridge",
            {"bridge_id":"bridge-new-york","mode":"mock"},
            {"Origin":ORIGIN, "Content-Type":"application/json"})
        data=json.loads(body)
        self.assertEqual(status,200)
        self.assertFalse(data["provider_verified"])
        self.assertEqual(data["provider_api_calls"],0)
        self.assertTrue(all(v["name"].startswith("Fictional ") for v in data["places"]))
        self.assertTrue(all(v["agent_decision_is_automatic_approval"] is False
                            for v in data["places"]))

    def test_even_misconfigured_hosted_env_cannot_trigger_real_api(self):
        with patch.dict(os.environ, {"QLOO_API_KEY":"FAKE_KEY_NOT_REAL_123456",
             "QLOO_EVENT_QUOTA_APPROVED":"YES"}):
            for path,payload in (
                    ("/api/bridge",{"bridge_id":"bridge-new-york","mode":"live"}),
                    ("/api/execute",{"scene_id":"jazz-new-york","mode":"live"})):
                with self.subTest(path=path):
                    status,_,body=self.request("POST",path,payload,
                        {"Origin":ORIGIN,"Content-Type":"application/json"})
                    self.assertEqual(status,422)
                    self.assertEqual(json.loads(body)["error"],
                                     "VALIDATION_OR_PROVIDER_GATE_BLOCKED")
                    self.assertNotIn(b"FAKE_KEY",body)

    def test_host_and_forwarded_host_cannot_bypass_gate(self):
        for host in ("scout.example.test:443", "evil.example",
                     "127.0.0.1", "sub.scout.example.test"):
            with self.subTest(host=host):
                status,_,body=self.request("GET","/api/bridges",
                    headers={"Host":host,"X-Forwarded-Host":HOST})
                self.assertEqual(status,403)
                self.assertEqual(json.loads(body)["error"],"INVALID_LOOPBACK_HOST")

    def test_https_only_exact_origin_required_for_posts(self):
        variants=("", "null", "http://"+HOST,
                  "https://evil.example",ORIGIN+"/","https://sub."+HOST)
        for origin in variants:
            with self.subTest(origin=origin):
                headers={"Content-Type":"application/json"}
                if origin:headers["Origin"]=origin
                status,_,body=self.request("POST","/api/bridge",
                    {"bridge_id":"bridge-new-york","mode":"mock"},headers)
                self.assertEqual(status,403)
                self.assertEqual(json.loads(body)["error"],"CROSS_ORIGIN_DENIED")

    def test_public_browser_assets_have_no_external_scripts(self):
        for asset in ("/","/styles.css","/app.js"):
            with self.subTest(asset=asset):
                status,_,body=self.request("GET",asset)
                self.assertEqual(status,200)
                self.assertGreater(len(body),150)
                self.assertNotIn(b"QLOO_API_KEY",body)

    def test_api_no_cache_and_no_cors(self):
        status,h,body=self.request("GET","/api/bridges")
        self.assertEqual(status,200)
        self.assertEqual(h["Cache-Control"],"no-store")
        self.assertIsNone(h.get("Access-Control-Allow-Origin"))
        status,_,_=self.request("OPTIONS","/api/bridges")
        self.assertEqual(status,405)


if __name__ == "__main__":
    unittest.main()
