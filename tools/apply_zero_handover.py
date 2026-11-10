"""Safely patch standalone 0 as a global, deterministic human handover command.

Does not edit WhatsApp credentials, webhook processing, customer data, prompts,
price lists or the public website. Requires an exact, single source anchor.
"""
from pathlib import Path

path=Path("app.py")
original=path.read_text(encoding="utf-8")
anchor=(
    '    text = _normalise_menu_text(customer_message)\n'
    '    current = get_customer_menu_state(customer_number)\n'
)
replacement=(
    '    text = _normalise_menu_text(customer_message)\n'
    '    # Standalone 0 is always the human-handover command, even when the AI\n'
    '    # displayed a menu without setting a deterministic menu state.\n'
    '    # Never treat quantities like 0kg as the handover command.\n'
    '    if text == "0":\n'
    '        clear_customer_menu_state(customer_number)\n'
    '        return {"action": "JONES"}\n'
    '    current = get_customer_menu_state(customer_number)\n'
)
if original.count(anchor)!=1:
    raise SystemExit(f"Expected exactly one matching menu anchor; found {original.count(anchor)}; refused to change app")
patched=original.replace(anchor,replacement,1)
path.write_text(patched,encoding="utf-8")
print("PATCHED: one menu handler; standalone 0 bypasses state and OpenAI; existing handover remains intact")
