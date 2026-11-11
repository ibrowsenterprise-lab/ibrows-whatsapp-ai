from pathlib import Path
import ast
s=Path("app.py").read_text("utf-8")
t=ast.parse(s)
fn=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=="handle_local_human_handover")
for i,line in enumerate(s.splitlines(),1):
 if fn.lineno <=i <=fn.end_lineno:
  if any(word in line.lower() for word in ["secret","password","api_key","token","authorization","bearer"]):
   line="[sensitive expression removed]"
  print(f"{i:05d} {line[:240]}")
