"""Public /ai one-tap demo link tests — no network or customer data."""
import sys
import types
import unittest
from unittest.mock import patch

from public_ai_shortcut import (
    DEMO_WHATSAPP_MESSAGE,
    DEMO_WHATSAPP_URL,
    register_public_ai_shortcut,
)


class FakeRule:
    def __init__(self, rule):
        self.rule = rule


class FakeMap:
    def __init__(self):
        self.rules = []

    def iter_rules(self):
        return self.rules


class FakeApp:
    def __init__(self):
        self.url_map = FakeMap()
        self.registered = []

    def add_url_rule(self, route, endpoint=None, view_func=None, methods=None):
        self.registered.append((route, endpoint, view_func, methods))
        self.url_map.rules.append(FakeRule(route))


class OneTapTests(unittest.TestCase):
    def test_direct_to_verified_ai_number_with_working_menu_message(self):
        self.assertEqual(DEMO_WHATSAPP_MESSAGE, "Show me your menu")
        self.assertEqual(
            DEMO_WHATSAPP_URL,
            "https://wa.me/265883242594?text=Show%20me%20your%20menu",
        )
        self.assertNotIn("265882242594", DEMO_WHATSAPP_URL)

    def test_get_link_redirects_without_autosending_or_collecting_input(self):
        app = FakeApp()
        self.assertTrue(register_public_ai_shortcut(app))
        self.assertEqual(len(app.registered), 1)
        route, _, view, methods = app.registered[0]
        self.assertEqual(route, "/ai")
        self.assertEqual(methods, ["GET"])
        with patch.dict(sys.modules, {
            "flask": types.SimpleNamespace(redirect=lambda url, code: (url, code))
        }):
            self.assertEqual(view(), (DEMO_WHATSAPP_URL, 302))

    def test_registration_idempotent_and_does_not_override_existing_route(self):
        app = FakeApp()
        self.assertTrue(register_public_ai_shortcut(app))
        self.assertFalse(register_public_ai_shortcut(app))
        self.assertEqual(len(app.registered), 1)

    def test_leaves_pre_existing_ai_route_untouched(self):
        app = FakeApp()
        app.url_map.rules.append(FakeRule("/ai"))
        self.assertFalse(register_public_ai_shortcut(app))
        self.assertEqual(app.registered, [])


if __name__ == "__main__":
    unittest.main()
