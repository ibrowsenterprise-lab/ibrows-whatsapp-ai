"""Read-only, minimal source inspection for customer Resume AI command."""
import ast
from pathlib import Path

lines=Path("app.py").read_text(encoding="utf-8").splitlines()
tree=ast.parse("\n".join(lines))
ranges=[]
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and any(q in node.name.lower() for q in ("ai_paused","resume_ai","unpause_ai","menu_state","receive_webhook")):
        print("FUNC",node.name,"start",node.lineno,"end",node.end_lineno)
        if node.name=="receive_webhook":
            ranges.append((node.lineno, min(node.lineno+160,node.end_lineno)))
        else:
            ranges.append((node.lineno,min(node.end_lineno,node.lineno+85)))
for i,line in enumerate(lines,1):
    if ("set_ai_paused(" in line or "resume ai" in line.lower() or "AI PAUSED FOR CUSTOMER" in line
        or "AI PAUSE" in line or "ai_paused" in line and i<9000):
        ranges.append((max(1,i-8),min(len(lines),i+12)))
merged=[]
for lo,hi in sorted(ranges):
    if merged and lo<=merged[-1][1]:
        merged[-1]=(merged[-1][0],max(merged[-1][1],hi))
    else:merged.append((lo,hi))
count=0
for lo,hi in merged:
    print("RANGE",lo,hi)
    for i in range(lo,hi+1):
        row=lines[i-1]
        if any(w in row.lower() for w in ("token","password","api_key","secret","authorization")):
            row="[omitted potential credential]"
        print(f"{i:05d} {row[:240]}")
        count+=1
        if count>400:break
    if count>400:break
print("PRINTED_LINES",count)
