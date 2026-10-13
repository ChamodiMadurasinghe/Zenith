import unittest

from core.update_checker import is_newer, parse_version


class TestUpdateChecker(unittest.TestCase):
    def test_parse_version_strips_v(self):
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("1.0"), (1, 0))

    def test_is_newer(self):
        self.assertTrue(is_newer("v1.2.0", "1.0.0"))
        self.assertFalse(is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(is_newer("0.9.0", "1.0.0"))
        self.assertTrue(is_newer("1.0.1", "1.0"))
