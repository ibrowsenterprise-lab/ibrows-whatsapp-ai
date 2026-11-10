"""Public-facing WhatsApp number migration for the November 2026 launch.

The API-enabled number has been verified with a live incoming/outgoing
WhatsApp test. This module changes only public HTML; it never changes the
Meta API phone-number ID, webhook configuration, database, or legacy line.
"""

ACTIVE_PUBLIC_WHATSAPP = "265883242594"
PREVIOUS_PUBLIC_WHATSAPP = "265882242594"

_REPLACEMENTS = (
    ("wa.me/265882242594", "wa.me/265883242594"),
    ("api.whatsapp.com/send?phone=265882242594",
     "api.whatsapp.com/send?phone=265883242594"),
    ("api.whatsapp.com/send/?phone=265882242594",
     "api.whatsapp.com/send/?phone=265883242594"),
    ("+265 882 242 594", "+265 883 242 594"),
    ("+265882242594", "+265883242594"),
    ("0882242594", "0883242594"),
)


def rewrite_public_whatsapp_html(html: str) -> str:
    """Route public click-to-chat links and displayed WhatsApp number to AI."""
    for previous, active in _REPLACEMENTS:
        html = html.replace(previous, active)
    return html
