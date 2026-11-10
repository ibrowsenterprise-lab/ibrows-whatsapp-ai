"""Read-only audit of payment posting and entitlement for paid service enquiries."""
import ast
from pathlib import Path
s=Path("app.py").read_text(encoding="utf-8").splitlines()
t=ast.parse("\n".join(s))
targets=[
"lead_payments", "record_lead_payment", "admin_lead_payment", "payment confirmed",
"mark as paid", "payment received", "service_started_at", "scholarship eligibility",
"eligibility check", "NOT_PAID", "payment verification", "get_paid_service",
"get_lead_financial", "admin_leads", "admin_lead",
]
print("FILE_LINES",len(s))
funcs={}
for n in ast.walk(t):
    if isinstance(n,ast.FunctionDef):
        funcs[n.name]=(n.lineno,n.end_lineno)
for name,span in funcs.items():
    if any(tok in name.lower() for tok in ["payment", "entitlement", "paid", "scholarship","lead"]):
        if "payment" in name.lower() or "entitlement" in name.lower() or "scholarship" in name.lower() or name.startswith("admin_lead"):
            print("FUNC",name,*span)
matches=[]
for i,l in enumerate(s,1):
    if any(w.lower() in l.lower() for w in targets):
        matches.append(i)
print("MATCHES",len(matches))
# Report only selected code blocks; never output credentials, sensitive raw customer data or stack variables.
sel=[]
for i in matches:
    line=s[i-1]
    if any(w in line.lower() for w in ["@app.route(", "create_payment","def record_lead_payment",
        "def admin_lead_payment","lead_payments","service_started_at","eligibility check", "not_paid",
        "admin_leads","admin_lead","payment confirmation","payment verification"]):
        sel.append(i)
for i in sel[:100]:
    lo=max(1,i-5); hi=min(len(s),i+10)
    print(f"BLOCK {lo}-{hi}")
    for j in range(lo,hi+1):
        line=s[j-1]
        if any(w in line.lower() for w in ("api_key","secret","authorization","password","access_token")):
            print(f"{j:05d} [omitted potential credential]")
        else: print(f"{j:05d} {line[:190]}")
print("BLOCK_COUNT",len(sel))

print("=== FOCUSED ADMIN WORKFLOW ===")
for lo,hi in [(11946,12090),(13770,13875),(13915,13940),(14052,14125),
               (16060,16125),(6238,6302),(9773,9835)]:
    print("SECTION",lo,hi)
    for i in range(lo,hi+1):
        row=s[i-1]
        if any(w in row.lower() for w in ("secret","api_key","authorization","access_token","password")):
            row="[omitted sensitive]"
        print(f"{i:05d} {row[:210]}")

print("=== SPECIFIC PAYMENT UI / POST ROUTES ===")
for lo,hi in [(13940,14049),(16060,16122),(11670,11732),
               (11810,11880),(27962,28025),(6609,6688)]:
    print("SHORT_RANGE",lo,hi)
    for i in range(lo,hi+1):
        line=s[i-1]
        if any(w in line.lower() for w in ("api_key","secret","authorization","access_token","password")):
            line="[sensitive omitted]"
        print(f"{i:05d} {line[:270]}")
