import unittest

from tests.dbhelp import db, fresh_db


class Identities(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db()
        self.sid = db.upsert_subscriber(self.conn, "dom@example.com", 3,
                                        "beginner", False, "monthly")

    def test_an_identity_leads_back_to_its_subscriber(self):
        db.add_identity(self.conn, self.sid, "apple", "001.abc", "x@y.com")
        found = db.get_identity_subscriber(self.conn, "apple", "001.abc")
        self.assertEqual(found["email"], "dom@example.com")

    def test_adding_the_same_identity_twice_keeps_one_row(self):
        for _ in range(2):
            db.add_identity(self.conn, self.sid, "google", "g-1", None)
        n = self.conn.execute(
            "SELECT COUNT(*) AS n FROM auth_identities").fetchone()["n"]
        self.assertEqual(n, 1)

    def test_an_unknown_identity_is_nobody(self):
        self.assertIsNone(db.get_identity_subscriber(self.conn, "apple", "nope"))
        # Same subject, other provider: subjects are only unique per provider.
        db.add_identity(self.conn, self.sid, "apple", "same", None)
        self.assertIsNone(db.get_identity_subscriber(self.conn, "google", "same"))

    def test_get_by_id(self):
        self.assertEqual(db.get_by_id(self.conn, self.sid)["email"],
                         "dom@example.com")
        self.assertIsNone(db.get_by_id(self.conn, 999))


if __name__ == "__main__":
    unittest.main()
