"""Verifying what Apple and Google say. Nothing here reaches either."""
import hashlib
import time
import unittest
from unittest import mock

import providers
from tests.keys import (BUNDLE_ID, D, RAW_NONCE, SERVICES_ID, apple_claims,
                        google_id_token, jwks, sign)

AUDS = [BUNDLE_ID, SERVICES_ID]


class Apple(unittest.TestCase):
    def setUp(self):
        providers._APPLE_JWKS_CACHE.clear()
        patcher = mock.patch.object(providers, "_fetch_apple_jwks", jwks)
        patcher.start()
        self.addCleanup(patcher.stop)

    def refused(self, token, nonce=RAW_NONCE):
        with self.assertRaises(providers.ProviderError):
            providers.verify_apple(token, nonce, AUDS)

    def test_a_good_token_yields_the_identity(self):
        ident = providers.verify_apple(sign(apple_claims()), RAW_NONCE, AUDS)
        self.assertEqual((ident.provider, ident.subject_id, ident.email,
                          ident.email_verified),
                         ("apple", "001234.abcdef", "dom@example.com", True))

    def test_the_string_false_reads_as_unverified(self):
        """Read naively, "false" is truthy -- and a verified address is
        what permits linking to an existing account."""
        ident = providers.verify_apple(
            sign(apple_claims(email_verified="false")), RAW_NONCE, AUDS)
        self.assertFalse(ident.email_verified)

    def test_a_signature_from_another_key_is_refused(self):
        self.refused(sign(apple_claims(), key_d=D - 2))

    def test_expired_foreign_and_misissued_tokens_are_refused(self):
        self.refused(sign(apple_claims(exp=int(time.time()) - 60)))
        self.refused(sign(apple_claims(aud="com.someone.else")))
        self.refused(sign(apple_claims(iss="https://accounts.google.com")))
        self.refused(sign(apple_claims(), kid="not-a-key"))

    def test_both_the_bundle_id_and_the_services_id_are_accepted(self):
        providers.verify_apple(sign(apple_claims(aud=SERVICES_ID)),
                               RAW_NONCE, AUDS)

    def test_a_different_nonce_is_refused(self):
        self.refused(sign(apple_claims()), nonce="a-different-nonce")

    def test_the_hash_itself_is_not_accepted_as_the_nonce(self):
        """Anyone holding a captured token can read the hash out of it."""
        self.refused(sign(apple_claims()),
                     nonce=hashlib.sha256(RAW_NONCE.encode()).hexdigest())

    def test_an_unreachable_apple_never_passes(self):
        providers._APPLE_JWKS_CACHE.clear()
        with mock.patch.object(providers, "_fetch_apple_jwks",
                               side_effect=RuntimeError("no network")):
            self.refused(sign(apple_claims()))

    def test_rubbish_is_refused_rather_than_crashing(self):
        for junk in ("", "x", "a.b", "a.b.c", "....", "a.b.c.d"):
            self.refused(junk)


class Google(unittest.TestCase):
    def exchange(self, body):
        response = mock.Mock()
        response.json.return_value = body
        with mock.patch.object(providers.httpx, "post",
                               return_value=response) as post:
            ident = providers.verify_google("code", "https://x/cb", "id", "secret")
        return ident, post

    def test_a_successful_exchange_yields_the_identity(self):
        ident, post = self.exchange({"id_token": google_id_token()})
        self.assertEqual((ident.subject_id, ident.email_verified),
                         ("g-sub-1", True))
        self.assertEqual(post.call_args.kwargs["data"]["client_secret"], "secret")

    def test_bad_exchanges_are_refused(self):
        for body in ({"error": "invalid_grant"},
                     {"id_token": google_id_token(aud="other")},
                     {"id_token": google_id_token(iss="evil")},
                     {"id_token": google_id_token(exp=int(time.time()) - 5)},
                     {"id_token": google_id_token(sub="")},
                     {"id_token": "junk"}):
            with self.assertRaises(providers.ProviderError, msg=body):
                self.exchange(body)


class Relay(unittest.TestCase):
    def test_apple_relay_addresses_are_recognised(self):
        self.assertTrue(providers.is_relay("a1b2@privaterelay.appleid.com"))
        self.assertTrue(providers.is_relay("A1B2@PrivateRelay.AppleID.com "))
        self.assertFalse(providers.is_relay("dom@example.com"))
        self.assertFalse(providers.is_relay(None))


if __name__ == "__main__":
    unittest.main()
