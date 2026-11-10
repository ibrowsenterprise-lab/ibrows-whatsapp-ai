"""Read-only, source-only inspection of WhatsApp menu and handover controls."""
import ast
from pathlib import Path
s=Path("app.py").read_text(encoding="utf-8").splitlines()
tree=ast.parse("\n".join(s))
needles=("Please choose a valid menu option", "menu option from 1 to", "Talk to Jones", "talk to a human",
         "record_human_handover_on_current_lead", "show me your menu", "MENU OPTIONS",
         "select a service", "menu_choice", "MENU_ITEMS", "HUMAN_HANDOVER")
starts=[]
for i,line in enumerate(s):
    lo=line.lower()
    if any(n.lower() in lo for n in needles):
        # Avoid printing any sensitive actual constants in unrelated regions.
        if 5000<=i<=22000 or "Please choose" in line or "Talk to Jones" in line:
            starts.append(i)
def safe(line):
    if any(w in line.lower() for w in ('api_key', 'whatsapp_token', 'authorization', 'access_token', 'password=', 'secret=')):
        return "[omitted potential secret]"
    return line[:250]
ranges=[]
for i in starts[:80]:
    lo=max(0,i-10); hi=min(len(s),i+17)
    ranges.append((lo,hi))
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in ("record_human_handover_on_current_lead","receive_webhook","generate_ai_reply"):
        print("FUNC",node.name,node.lineno,node.end_lineno)
        if node.name=="record_human_handover_on_current_lead":
            ranges.append((node.lineno-1,node.end_lineno))
        elif node.name=="receive_webhook":
            ranges.append((node.lineno-1,min(node.lineno+115,node.end_lineno)))
merged=[]
for lo,hi in sorted(ranges):
    if merged and lo<=merged[-1][1]+2:
        merged[-1]=(merged[-1][0],max(merged[-1][1],hi))
    else:
        merged.append((lo,hi))
n=0
for lo,hi in merged:
    print("BLOCK",lo+1,hi)
    for j in range(lo,hi):
        if n>700: break
        print(f"{j+1:05d} {safe(s[j])}")
        n+=1
    if n>700:break
print("LINES_PRINTED",n,"MATCHES",len(starts))
