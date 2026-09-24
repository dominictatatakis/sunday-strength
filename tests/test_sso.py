"""Who a Google or Apple sign-in belongs to. Providers are stubbed."""
import unittest
from unittest import mock

from tests.dbhelp import db, fresh_db

import app as app_module  # noqa: E402  (after dbhelp has set the env)
import providers  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PREFS = {"days": 3, "experience": "beginner", "run": False,
         "equipment": "dumbbells", "plan": "monthly"}


def ident(email="dom@example.com", verified=True, sub="g-sub-1",
          provider="google"):
    return providers.ProviderIdentity(provider, sub, email, verified)


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db()
        for name, value in (("GOOGLE_ENABLED", True),
                            ("GOOGLE_CLIENT_ID", "id"),
                            ("GOOGLE_CLIENT_SECRET", "secret")):
            p = mock.patch.object(app_module, name, value)
            p.start()
            self.addCleanup(p.stop)
        app_module.ratelimit._hits.clear() if hasattr(
            app_module.ratelimit, "_hits") else None
        self.client = TestClient(app_module.app)

    def google_says(self, who):
        p = mock.patch.object(providers, "verify_google",
                              lambda *a, **k: who)
        p.start()
        self.addCleanup(p.stop)

    def callback(self, state):
        return self.client.get(
            f"/auth/google?code=abc&state={db.sign_data(state)}",
            follow_redirects=False)

    def count(self, table):
        return self.conn.execute(
            f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]

    def password_account(self, email="dom@example.com"):
        sid = db.upsert_subscriber(self.conn, email, 4, "advanced", True,
                                   "monthly", "full")
        db.set_password(self.conn, email, "hunter22hunter22")
        return sid


class Resolving(Base):
    def test_a_known_identity_is_that_subscriber(self):
        sid = self.password_account()
        db.add_identity(self.conn, sid, "apple", "001.x", "relay@privaterelay.appleid.com")
        sub, problem, _ = app_module._resolve_identity(
            self.conn, ident("relay@privaterelay.appleid.com", sub="001.x",
                             provider="apple"), None, from_app=True)
        self.assertEqual((sub["id"], problem), (sid, None))

    def test_a_relay_address_never_links(self):
        """Even to a subscriber who holds that exact relay address."""
        self.password_account("abc@privaterelay.appleid.com")
        sub, problem, _ = app_module._resolve_identity(
            self.conn, ident("abc@privaterelay.appleid.com", sub="001.y",
                             provider="apple"), None, from_app=True)
        self.assertIsNone(sub)
        self.assertEqual(problem, "needs_onboarding")
        self.assertEqual(self.count("auth_identities"), 0)

    def test_no_preferences_means_nothing_is_written(self):
        sub, problem, _ = app_module._resolve_identity(
            self.conn, ident(), None, from_app=True)
        self.assertEqual((sub, problem), (None, "needs_onboarding"))
        self.assertEqual(self.count("subscribers"), 0)

    def test_an_unverified_email_neither_links_nor_creates(self):
        self.password_account()
        for prefs in (None, PREFS):
            sub, problem, _ = app_module._resolve_identity(
                self.conn, ident(verified=False, email="other@example.com"),
                prefs, from_app=True)
            self.assertIsNone(sub)
        sub, problem, _ = app_module._resolve_identity(
            self.conn, ident(verified=False), PREFS, from_app=True)
        self.assertIsNone(sub)
        self.assertEqual(self.count("subscribers"), 1)
        self.assertEqual(self.count("auth_identities"), 0)

    def test_new_accounts_from_the_app_only_while_payments_are_off(self):
        with mock.patch.object(app_module, "DEV_MODE", False):
            sub, problem, _ = app_module._resolve_identity(
                self.conn, ident(), PREFS, from_app=True)
        self.assertEqual((sub, problem), (None, "no_account"))
        self.assertEqual(self.count("subscribers"), 0)

    def test_a_taken_address_is_not_given_a_second_account(self):
        """Verified but different provider subject and a relay: the relay
        address is held by someone else already, so no second row."""
        self.password_account("abc@privaterelay.appleid.com")
        sub, problem, _ = app_module._resolve_identity(
            self.conn, ident("abc@privaterelay.appleid.com", sub="001.z",
                             provider="apple"), PREFS, from_app=True)
        self.assertEqual((sub, problem), (None, "email_in_use"))

    def test_preferences_create_the_account_and_the_identity(self):
        sub, problem, created = app_module._resolve_identity(
            self.conn, ident(), PREFS, from_app=True)
        self.assertIsNone(problem)
        self.assertTrue(created)
        self.assertEqual((sub["days_per_week"], sub["equipment"]),
                         (3, "dumbbells"))
        self.assertEqual(self.count("auth_identities"), 1)


class WebCallback(Base):
    def test_an_existing_password_account_links_on_first_google_sign_in(self):
        sid = self.password_account()
        self.conn.execute(
            "INSERT INTO completions (subscriber_id, week, day, slug) "
            "VALUES (?, '2026-W39', 1, 'goblet-squat')", (sid,))
        self.conn.commit()
        self.google_says(ident())
        r = self.callback({"login": True})
        self.assertEqual(r.headers["location"], "/account")
        self.assertIn(app_module.SESSION_COOKIE, r.cookies)
        self.assertEqual(self.count("subscribers"), 1)
        self.assertEqual(self.count("completions"), 1)
        self.assertEqual(db.get_identity_subscriber(
            self.conn, "google", "g-sub-1")["id"], sid)

    def test_signing_in_twice_keeps_one_identity(self):
        self.password_account()
        self.google_says(ident())
        self.callback({"login": True})
        self.callback({"login": True})
        self.assertEqual(self.count("auth_identities"), 1)

    def test_web_signup_carries_preferences_through_google(self):
        self.google_says(ident(email="new@example.com"))
        r = self.callback({"signup": True, "days": 3,
                           "experience": "beginner", "run": False,
                           "plan": "monthly", "equipment": "dumbbells"})
        self.assertEqual(r.headers["location"], "/success?dev=1")
        sub = db.get_by_email(self.conn, "new@example.com")
        self.assertEqual((sub["days_per_week"], sub["status"]), (3, "active"))

    def test_plain_login_by_someone_new_fails_without_writing(self):
        self.google_says(ident(email="new@example.com"))
        r = self.callback({"login": True})
        self.assertIn("sso=failed", r.headers["location"])
        self.assertEqual(self.count("subscribers"), 0)

    def test_a_refused_code_fails_cleanly(self):
        def refuse(*a, **k):
            raise providers.ProviderError("no")
        with mock.patch.object(providers, "verify_google", refuse):
            r = self.callback({"login": True})
        self.assertIn("sso=failed", r.headers["location"])

    def test_a_state_we_did_not_sign_is_refused(self):
        self.google_says(ident())
        r = self.client.get("/auth/google?code=abc&state=forged",
                            follow_redirects=False)
        self.assertIn("sso=failed", r.headers["location"])




from tests.keys import RAW_NONCE, apple_claims, jwks, sign  # noqa: E402

APP_PREFS = {"days": 3, "experience": "beginner", "run": False,
             "equipment": "dumbbells"}


class Phone(Base):
    def setUp(self):
        super().setUp()
        providers._APPLE_JWKS_CACHE.clear()
        p = mock.patch.object(providers, "_fetch_apple_jwks", jwks)
        p.start()
        self.addCleanup(p.stop)

    def apple(self, prefs=None, **claims):
        body = {"identity_token": sign(apple_claims(**claims)),
                "nonce": RAW_NONCE}
        if prefs is not None:
            body["prefs"] = prefs
        return self.client.post("/api/v1/auth/apple", json=body)

    def test_the_server_says_which_providers_are_on(self):
        self.assertEqual(self.client.get("/api/v1/auth/providers").json(),
                         {"google": True, "apple": True})
        with mock.patch.object(app_module, "GOOGLE_ENABLED", False):
            self.assertFalse(
                self.client.get("/api/v1/auth/providers").json()["google"])

    def test_someone_new_is_asked_the_four_questions_first(self):
        r = self.apple()
        self.assertEqual((r.status_code, r.json()["error"]),
                         (409, "needs_onboarding"))
        self.assertEqual(self.count("subscribers"), 0)

    def test_apple_with_preferences_creates_an_active_account(self):
        r = self.apple(APP_PREFS)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["refresh"])
        sub = db.get_by_email(self.conn, "dom@example.com")
        self.assertEqual((sub["status"], sub["equipment"]),
                         ("active", "dumbbells"))
        # The cookie it set is a working session for the existing API.
        self.assertEqual(self.client.get("/api/v1/me").status_code, 200)

    def test_bad_preferences_are_refused_and_write_nothing(self):
        for prefs in ({"days": 9, "experience": "beginner", "run": False,
                       "equipment": "full"},
                      {"days": 3, "experience": "guru", "run": False,
                       "equipment": "full"},
                      {"days": "3"}, "junk"):
            self.assertEqual(self.apple(prefs).status_code, 400, prefs)
        self.assertEqual(self.count("subscribers"), 0)

    def test_a_bad_apple_token_is_401(self):
        r = self.client.post("/api/v1/auth/apple",
                             json={"identity_token": "x", "nonce": RAW_NONCE})
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/v1/auth/apple", json={
            "identity_token": sign(apple_claims()), "nonce": "replayed"})
        self.assertEqual(r.status_code, 401)

    def test_payments_on_means_no_new_accounts_from_the_phone(self):
        with mock.patch.object(app_module, "DEV_MODE", False):
            r = self.apple(APP_PREFS)
        self.assertEqual((r.status_code, r.json()["error"]),
                         (403, "no_account"))

    def test_an_existing_subscriber_signs_straight_in(self):
        self.password_account()
        r = self.apple()
        self.assertEqual(r.status_code, 200)

    def test_a_refresh_token_brings_back_a_session(self):
        refresh = self.apple(APP_PREFS).json()["refresh"]
        fresh = TestClient(app_module.app)
        self.assertEqual(fresh.get("/api/v1/me").status_code, 401)
        r = fresh.post("/api/v1/auth/refresh", json={"refresh": refresh})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(fresh.get("/api/v1/me").status_code, 200)

    def test_no_other_signed_blob_passes_as_a_refresh_token(self):
        sid = self.password_account()
        for blob in (db.sign_data({"login": True, "app": True}),
                     db.sign_data({"handoff": sid}),
                     db.sign_data({"pending": {"subject_id": "x"}}),
                     "forged", ""):
            r = self.client.post("/api/v1/auth/refresh", json={"refresh": blob})
            self.assertEqual(r.status_code, 401, blob)


class PhoneGoogle(Base):
    def app_callback(self):
        return self.callback({"login": True, "app": True})

    def test_the_app_start_carries_app_in_signed_state(self):
        r = self.client.get("/login/google?app=1", follow_redirects=False)
        state = urllib.parse.parse_qs(
            urllib.parse.urlparse(r.headers["location"]).query)["state"][0]
        self.assertTrue(db.verify_data(state)["app"])

    def test_the_phone_gets_a_handoff_never_a_session(self):
        self.password_account()
        self.google_says(ident())
        r = self.app_callback()
        loc = r.headers["location"]
        self.assertTrue(loc.startswith("sundaystrength://auth?handoff="))
        self.assertNotIn(app_module.SESSION_COOKIE, r.cookies)
        handoff = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["handoff"][0]
        r = self.client.post("/api/v1/auth/google", json={"handoff": handoff})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["refresh"])

    def test_a_stale_or_forged_handoff_is_refused(self):
        sid = self.password_account()
        stale = db.sign_data({"handoff": sid})
        with mock.patch("time.time", return_value=__import__("time").time() + 61):
            r = self.client.post("/api/v1/auth/google", json={"handoff": stale})
        self.assertEqual(r.status_code, 401)
        for blob in ("forged", db.sign_data({"refresh": sid})):
            r = self.client.post("/api/v1/auth/google", json={"handoff": blob})
            self.assertEqual(r.status_code, 401)

    def test_someone_new_comes_back_to_onboard_then_finishes(self):
        self.google_says(ident(email="new@example.com"))
        loc = self.app_callback().headers["location"]
        self.assertTrue(loc.startswith("sundaystrength://auth?needs_onboarding=1"))
        pending = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["pending"][0]
        self.assertEqual(self.count("subscribers"), 0)
        r = self.client.post("/api/v1/auth/google",
                             json={"pending": pending, "prefs": APP_PREFS})
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(db.get_by_email(self.conn, "new@example.com"))

    def test_a_forged_pending_identity_is_refused(self):
        r = self.client.post("/api/v1/auth/google", json={
            "pending": "made-up", "prefs": APP_PREFS})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.count("subscribers"), 0)

    def test_a_failed_app_sign_in_goes_back_to_the_app(self):
        r = self.client.get("/auth/google?error=access_denied&state="
                            + db.sign_data({"login": True, "app": True}),
                            follow_redirects=False)
        self.assertEqual(r.headers["location"], "sundaystrength://auth?error=1")


import urllib.parse  # noqa: E402

if __name__ == "__main__":
    unittest.main()
