import ast
from pathlib import Path
s=Path("app.py").read_text("utf-8").splitlines()
t=ast.parse("\n".join(s))
funcs=[(n.name,n.lineno,n.end_lineno) for n in t.body if isinstance(n,ast.FunctionDef)]
for name,start,end in funcs:
 if any(k in name.lower() for k in ["handover","notification","notify","takeover","inbox","send_whatsapp"]):
  print("FUNC",name,start,end)
for i,line in enumerate(s,1):
 if "record_human_handover_on_current_lead(" in line or "human handover" in line.lower() or "human takeover" in line.lower():
  print("HIT",i,line[:150])
for name,start,end in funcs:
 if name in ("record_human_handover_on_current_lead","record_human_handover","receive_webhook","send_whatsapp_message","send_admin_notification","notify_admin"):
  print("SECTION",name,start,end)
  if name=="receive_webhook": 
   for i in range(start,end+1):
    row=s[i-1]
    if any(k in row.lower() for k in ["handover","human","notify","pause","\"0\"","'0'","message"]):
     lo=max(start,i-4); hi=min(end,i+8)
     print("WINDOW",lo,hi)
     for j in range(lo,hi+1):
      row=s[j-1]
      if any(w in row.lower() for w in ["secret","api_key","password","access_token","authorization"]):row="[redacted]"
      print(f"{j:05d} {row[:195]}")
  else:
   for i in range(start,min(end,start+125)+1):
    row=s[i-1]
    if any(w in row.lower() for w in ["secret","api_key","password","access_token","authorization"]):row="[redacted]"
    print(f"{i:05d} {row[:195]}")
