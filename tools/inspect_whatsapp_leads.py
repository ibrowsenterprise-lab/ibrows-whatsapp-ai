"""Read-only WhatsApp lead-flow inventory. Never import app.py or access secrets."""
import ast
from pathlib import Path

source = Path("app.py").read_text(encoding="utf-8")
lines = source.splitlines()
tree = ast.parse(source)
functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
watch = ("whatsapp", "webhook", "lead", "classify", "sales", "ai_reply")
print("FUNCTION INDEX")
for n in functions:
    if any(word in n.name.lower() for word in watch):
        print(n.name, n.lineno, n.end_lineno)
print("TARGETED LEAD FLOW")
targets = ["AI STRUCTURED OUTPUT VALIDATED", "lead_required", "General Enquiry"]
matches = [i for i,s in enumerate(lines) if any(t in s for t in targets)]
print("matched lines", len(matches))
shown=set()
for i in matches[:28] + matches[-12:]:
    for j in range(max(0,i-2), min(len(lines),i+3)):
        if j in shown: continue
        shown.add(j)
        s=lines[j].strip()
        if any(w in s.lower() for w in ["token", "secret", "password", "api_key", "authorization"]):
            s="[redacted credential-related line]"
        if len(s)>190: s=s[:190]+"..."
        print(f"{j+1}: {s}")
