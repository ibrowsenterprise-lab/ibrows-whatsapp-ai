"""Read-only, sanitized static inspection of CRM lead rendering and payment summaries."""
import ast
from pathlib import Path
src=Path("app.py").read_text("utf-8")
lines=src.splitlines()
tree=ast.parse(src)
for n in tree.body:
    if isinstance(n,ast.FunctionDef) and (n.name in ("admin_leads","admin_lead_operations","get_verified_service_payment_state","admin_customer_history","create_or_update_lead","_crm_apply_lead_row","admin_lead_status") or "pipeline" in n.name.lower()):
        print("FUNCTION",n.name,n.lineno,n.end_lineno)
# line ranges around static HTML labels / template fields
terms=[
"Open estimated value","Needs Attention","Needs attention","Open lead",
"Payments received","Outstanding accepted balance","handover_reason",
"{{ lead.summary", "{{ lead.handover_reason", "admin_leads", "open_estimated",
"pipeline", "accepted_value",
]
found={}
for term in terms:
    indexes=[i for i,row in enumerate(lines,1) if term in row]
    found[term]=indexes
    print("INDEX",term, indexes[:35], "total",len(indexes))
selected=[]
for term in terms:
    for i in found[term][:8]:
        if term in ("pipeline","admin_leads","handover_reason"):
            lo=max(1,i-5);hi=min(i+8,len(lines))
        else:
            lo=max(1,i-13);hi=min(i+25,len(lines))
        selected.append((lo,hi,term))
selected=sorted(selected,key=lambda x:x[0])
ranges=[]
for lo,hi,k in selected:
    if ranges and lo<=ranges[-1][1]+1:
        ranges[-1]=(ranges[-1][0],max(ranges[-1][1],hi))
    else:
        ranges.append((lo,hi))
total=0
for lo,hi in ranges:
    print("SOURCE_RANGE",lo,hi)
    for i in range(lo,hi+1):
        row=lines[i-1]
        if any(x in row.lower() for x in ("api_key", "secret", "authorization","password","access_token","webhook_token")):
            row="[sanitized code line]"
        print(f"{i:05d} {row[:210]}")
        total+=1
        if total>=550:break
    if total>=550:break
print("SOURCE_PRINTED",total)
