"""Offline launch tests: no real Meta messages, client records, or network."""
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from launch_contact_config import rewrite_public_whatsapp_html

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    status_code = 200
    mimetype = "text/html"

    def __init__(self, html):
        self.html = html

    def get_data(self, as_text=False):
        return self.html if as_text else self.html.encode()

    def set_data(self, html):
        self.html = html


class FakeApp:
    def after_request(self, function):
        self.hook = function
        return function


class ContactLaunchTests(unittest.TestCase):
    def test_changes_every_known_public_whatsapp_link_but_keeps_message(self):
        html = ('<a href="https://wa.me/265882242594?text=Hello+IBROWS">'
                'WhatsApp us</a> WhatsApp: +265 882 242 594')
        result = rewrite_public_whatsapp_html(html)
        self.assertIn('wa.me/265883242594?text=Hello+IBROWS', result)
        self.assertIn('+265 883 242 594', result)
        self.assertNotIn('265882242594', result)

    def test_other_numbers_and_official_email_unchanged(self):
        html = 'Call +265 999 111 222 info@ibrowsenterprise.com'
        self.assertEqual(rewrite_public_whatsapp_html(html), html)

    def test_rewrite_idempotent(self):
        html = '<a href="https://wa.me/265882242594">Chat</a>'
        first = rewrite_public_whatsapp_html(html)
        self.assertEqual(first, rewrite_public_whatsapp_html(first))

    def test_public_hook_preserves_mitgo_and_never_touches_admin_or_webhook(self):
        app = FakeApp()
        config = runpy.run_path(str(ROOT / "gunicorn.conf.py"))
        config["post_worker_init"](types.SimpleNamespace(wsgi=app))
        request = types.SimpleNamespace(method="GET", path="/")
        fake_flask = types.SimpleNamespace(request=request)
        with patch.dict(sys.modules, {"flask": fake_flask}):
            resp = app.hook(FakeResponse(
                '<html><head></head><body>'
                '<a href="https://wa.me/265882242594">Chat</a>'
                '</body></html>'))
            self.assertIn("mitgo-verification", resp.html)
            self.assertIn("wa.me/265883242594", resp.html)
            first = resp.html
            self.assertEqual(app.hook(FakeResponse(first)).html, first)
            request.path = "/admin/leads"
            resp = app.hook(FakeResponse('https://wa.me/265882242594'))
            self.assertEqual(resp.html, 'https://wa.me/265882242594')
            request.path = "/webhook"
            self.assertEqual(
                app.hook(FakeResponse('https://wa.me/265882242594')).html,
                'https://wa.me/265882242594')
            request.path = "/"
            request.method = "POST"
            self.assertEqual(
                app.hook(FakeResponse('https://wa.me/265882242594')).html,
                'https://wa.me/265882242594')


if __name__ == "__main__":
    unittest.main()
