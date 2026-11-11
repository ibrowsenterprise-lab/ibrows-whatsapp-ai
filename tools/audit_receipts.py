"""Read-only static audit of production receipt/payment route. No app import."""
import ast
from pathlib import Path
s=Path('app.py').read_text("utf-8").splitlines()
t=ast.parse("\n".join(s))
fns=[(n.name,n.lineno,n.end_lineno) for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
for name,lo,hi in fns:
 if any(k in name.lower() for k in ("receipt","payment","invoice","lead_management","lead_operations","whatsapp_template","send_whatsapp_message")):
  print("FUNCTION",name,lo,hi)
for i,line in enumerate(s,1):
 if any(k in line.lower() for k in ("send_receipt","receipt_sent","receipt_issued","receipt_text","receipt_message","payment_confirmation","payment received","received payment","lead_payments")):
  if any(x in line.lower() for x in ("secret","password","access_token","api_key","authorization","bearer")): continue
  print("KEYWORD",i,line[:180])
for name,lo,hi in fns:
 if name in ("update_lead_management","admin_lead_operations","generate_payment_receipt","send_payment_receipt","send_whatsapp_message","get_verified_service_payment_state"):
  print("BLOCK",name,lo,hi)
  for i in range(lo,min(hi,lo+245)+1):
   row=s[i-1]
   if any(x in row.lower() for x in ("secret","password","access_token","api_key","authorization","bearer")):row="[redacted]"
   print(f"{i:05d} {row[:240]}")
