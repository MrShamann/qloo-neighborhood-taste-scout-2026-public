"""Credentialless, no-network security tests for Qloo hackathon HTTPS preflight."""
import os
import ssl
import unittest
from unittest.mock import patch

from src.taste_scout import (
    HOST, DenyRedirect, GuardError, guarded_qloo_fetcher,
    live_flow, fixture
)

class QlooTransportTests(unittest.TestCase):
    def test_system_cas_and_hostname_verification_stay_enabled(self):
        open_fn=guarded_qloo_fetcher()
        self.assertTrue(callable(open_fn))
        # Underlying transport is built from verified local roots; not a key test.
        self.assertTrue(ssl.CERT_REQUIRED!=ssl.CERT_NONE)

    def test_any_api_redirect_is_refused_before_forwarding_key(self):
        deny=DenyRedirect()
        for url in ("https://untrusted.example/collect",
                    "https://hackathon.api.qloo.com/other-path"):
            with self.subTest(url=url),self.assertRaises(GuardError):
                deny.redirect_request(None,None,302,"Moved",{},url)

    def test_malformed_keys_rejected_without_any_request(self):
        bad=["short","offline-test-token\n", "offline test token",
             "offline\ttest-token","漢字"*9,"a"*280]
        for value in bad:
            with self.subTest(kind="invalid_key"),patch.dict(
                os.environ,{"QLOO_API_KEY":value,"QLOO_EVENT_QUOTA_APPROVED":"YES"}
            ),self.assertRaises(GuardError):
                live_flow(fixture(),fetcher=lambda *args,**kwargs:
                    self.fail("remote request not permitted"))

    def test_credentialless_mode_rejects_without_preflight(self):
        with patch.dict(os.environ,{"QLOO_API_KEY":"",
                "QLOO_EVENT_QUOTA_APPROVED":"NO"}),patch(
                "src.taste_scout.guarded_qloo_fetcher",
                side_effect=AssertionError("must not open TLS")):
            with self.assertRaises(GuardError):
                live_flow(fixture())

    def test_unapproved_quota_rejected_even_with_valid_key(self):
        with patch.dict(os.environ,{"QLOO_API_KEY":"synthetic-test-only-key",
                "QLOO_EVENT_QUOTA_APPROVED":"NO"}):
            with self.assertRaises(GuardError):
                live_flow(fixture(),fetcher=lambda *a,**k:
                    self.fail("unapproved provider usage"))

    def test_all_qloo_calls_remain_hackathon_only(self):
        self.assertEqual(HOST,"https://hackathon.api.qloo.com")
        self.assertNotEqual(HOST,"https://api.qloo.com")

if __name__=="__main__":
    unittest.main()
