import unittest

from app import create_app


class TestLegalPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_privacy_public(self):
        resp = self.client.get("/privacy")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Privacy Policy", resp.data)

    def test_terms_public(self):
        resp = self.client.get("/terms")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Terms of Service", resp.data)

    def test_data_deletion_public(self):
        resp = self.client.get("/data-deletion")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"data deletion", resp.data.lower())


if __name__ == "__main__":
    unittest.main()
