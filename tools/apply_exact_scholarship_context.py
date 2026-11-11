"""Change only the authoritative one-off scholarship service ledger lookup."""
from pathlib import Path
p=Path("app.py")
s=p.read_text(encoding="utf-8")
old='''    scholarship_state = get_verified_service_payment_state(
        customer_number, "Scholarship Search"
    )
    lines.extend(scholarship_payment_context_lines(scholarship_state))
'''
new='''    # One-off Eligibility Check is a distinct paid service from shortlisting,
    # applications and monthly scholarship assistance.
    scholarship_state = get_verified_service_payment_state(
        customer_number, "Scholarship Eligibility Check", 5000
    )
    lines.extend(scholarship_payment_context_lines(scholarship_state))
'''
if s.count(old)!=1:raise SystemExit("Exact scholarship ledger lookup mismatch: refusing patch")
s=s.replace(old,new,1)
compile(s,"app.py","exec")
p.write_text(s,encoding="utf-8")
print("VERIFIED ONE-OFF ELIGIBILITY LEDGER LOOKUP UPDATED")
