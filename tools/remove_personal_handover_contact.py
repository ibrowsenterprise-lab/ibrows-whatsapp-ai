"""Exact, narrow source correction: keep business human handover in business chat."""
from pathlib import Path
p=Path("app.py")
s=p.read_text(encoding="utf-8")
old='''            f"If your message is personal or not related to IBROWS business, you can WhatsApp Jones directly on {JONES_PERSONAL_WHATSAPP_DISPLAY}. "
'''
replacement='''            "Please continue replying here; no separate number or saved contact is needed. "
'''
if s.count(old)!=1:
    raise SystemExit(f"Refusing handover response edit: expected exactly one source anchor, found {s.count(old)}")
s=s.replace(old,replacement,1)
compile(s,"app.py","exec")
p.write_text(s,"utf-8")
print("HUMAN HANDOVER CUSTOMER ACK: personal WhatsApp number no longer promoted; handover routes preserved")
