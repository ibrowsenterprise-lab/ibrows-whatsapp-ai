"""Short, owned URL for the public IBROWS WhatsApp AI demo.

Redirect-only, no request collection and no client information stored.
"""
from launch_contact_config import ACTIVE_PUBLIC_WHATSAPP

DEMO_WHATSAPP_MESSAGE = "Show me your menu"
DEMO_WHATSAPP_URL = (
    f"https://wa.me/{ACTIVE_PUBLIC_WHATSAPP}?text=Show%20me%20your%20menu"
)


def register_public_ai_shortcut(flask_app):
    """Register GET /ai without modifying existing routes or database."""
    if not hasattr(flask_app, "add_url_rule"):
        return False

    if any(getattr(rule, "rule", "") == "/ai"
           for rule in flask_app.url_map.iter_rules()):
        return False

    def _open_whatsapp_ai():
        from flask import redirect
        return redirect(DEMO_WHATSAPP_URL, code=302)

    flask_app.add_url_rule(
        "/ai",
        endpoint="ibrows_public_ai_one_tap_demo",
        view_func=_open_whatsapp_ai,
        methods=["GET"],
    )
    return True
