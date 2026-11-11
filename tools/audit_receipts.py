import ast
from pathlib import Path
s=Path("app.py").read_text("utf-8").splitlines()
t=ast.parse("\n".join(s))
for n in t.body:
 if isinstance(n,ast.FunctionDef) and any(k in n.name.lower() for k in ("business_document","send_whatsapp_document","service_window","whatsapp_media","payment")):
  if n.name in ("admin_business_document_send","admin_business_document_issue","get_or_create_business_document_record","_business_pdf_build","send_whatsapp_document","is_whatsapp_service_window_open"):
   print("FN",n.name,n.lineno,n.end_lineno)
for lo,hi in [(15895,16026),(21990,22095)]:
 print("RANGE",lo,hi)
 for i in range(lo,hi+1):
  row=s[i-1]
  if any(k in row.lower() for k in ("api_key","password","access_token","authorization","secret","bearer")):row="[redacted]"
  print(f"{i:05d} {row[:240]}")
