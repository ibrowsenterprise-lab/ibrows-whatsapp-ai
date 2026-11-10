"""Narrow, exact-match patch to include scholarship ledger facts in AI context."""
from pathlib import Path
p=Path("app.py")
old=p.read_text(encoding="utf-8")
anchor='''    if not any_open:
        lines.append("- No open paid-career-service ledger record is currently available for this customer.")

    career_assist = get_career_assist_lifecycle_state(customer_number)
'''
replacement='''    if not any_open:
        lines.append("- No open paid-career-service ledger record is currently available for this customer.")

    # Scholarship packages must use the same trusted CRM ledger as career
    # packages. A screenshot or customer message does NOT verify a payment.
    from scholarship_payment_context import scholarship_payment_context_lines
    scholarship_state = get_verified_service_payment_state(
        customer_number, "Scholarship Search"
    )
    lines.extend(scholarship_payment_context_lines(scholarship_state))

    career_assist = get_career_assist_lifecycle_state(customer_number)
'''
if old.count(anchor)!=1:
    raise SystemExit(f"Refusing app mutation: expected one verified-payment anchor, got {old.count(anchor)}")
new=old.replace(anchor,replacement,1)
compile(new,"app.py","exec")
p.write_text(new,encoding="utf-8")
print("SCHOLARSHIP LEDGER CONTEXT PATCHED: no changes to payment posting, webhooks, or data")
