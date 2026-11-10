"""Apply a narrow, repeatable fix for WhatsApp customer-controlled AI resume.

Runs in CI against the checked out 4.5MB app.py file, not against a live
database. Exactly two existing source anchors must match once each.
"""
from pathlib import Path
p=Path("app.py")
original=p.read_text(encoding="utf-8")
anchor1=(
'        if is_ai_paused(customer_number):\n'
'            # Keep a text-only record so the AI has context if automation resumes.\n'
)
block=(
'        # An explicit customer request to resume AI must work BEFORE the\n'
'        # paused-conversation gate. Only exact phrases trigger reactivation;\n'
'        # ordinary customer messages remain protected during human takeover.\n'
'        if message_type == "text" and " ".join(customer_message.lower().split()) in {\n'
'            "resume ai", "restart ai", "start ai", "enable ai", "resume bot",\n'
'        }:\n'
'            set_ai_paused(customer_number, False)\n'
'            clear_customer_menu_state(customer_number)\n'
'            reply = (\n'
'                "IBROWS AI Assistant is active again. You can now ask a question "\n'
'                "or send \\"Show me your menu\\" to explore services.\\n\\n"\n'
'                "To speak with Jones again, reply 0."\n'
'            )\n'
'            save_message(customer_number, "user", customer_message)\n'
'            save_message(customer_number, "assistant", reply)\n'
'            store_pending_reply(message_id, reply)\n'
'            sent = send_whatsapp_message(customer_number, reply)\n'
'            finish_whatsapp_message(message_id, sent)\n'
'            print("CUSTOMER SELF-SERVICE AI RESUMED", flush=True)\n'
'            return "EVENT_RECEIVED", 200\n'
'\n'
)
anchor2=(
'    # Pause first so the customer\\'s explicit preference is respected even\n'
'    # if lead recording or notification later fails.\n'
)
replacement2=(
'    # Show the return-to-AI option when a customer chooses human help.\n'
'    reply += "\\n\\nTo return to AI support later, send: Resume AI"\n'
'\n'
+anchor2
)
if original.count(anchor1)!=1 or original.count(anchor2)!=1:
    raise SystemExit(f"Refusing patch: paused={original.count(anchor1)} handover={original.count(anchor2)}")
new=original.replace(anchor1,block+anchor1,1).replace(anchor2,replacement2,1)
if len(new)-len(original)>2400:
    raise SystemExit("Refusing oversized patch")
p.write_text(new,encoding="utf-8")
print("PATCH APPLIED: resume command before pause gate; handover message includes resume instructions")
