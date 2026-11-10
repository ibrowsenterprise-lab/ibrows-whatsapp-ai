"""Static, read-only analysis of paid eligibility / chatbot entrypoint.

Never runs or imports app.py. Reports only functions and source excerpts, not any
customer data, tokens, production env vars, database connections or credentials.
"""
import ast
from pathlib import Path
lines=Path("app.py").read_text("utf-8").splitlines()
tree=ast.parse("\n".join(lines))
funcs={}
for node in tree.body:
    if isinstance(node,ast.FunctionDef):
        funcs[node.name]=(node.lineno,node.end_lineno)
for name,rg in funcs.items():
    if any(t in name.lower() for t in ("payment_context","service_payment_state","ai_reply","webhook","generate_ai_reply","menu","scholarship")):
        if name in ("build_verified_payment_context", "get_verified_service_payment_state","generate_ai_reply","receive_webhook","route_customer_menu_text","route_customer_menu","build_ai_system_prompt"):
            print("FUNCTION",name,*rg)
for name in ("get_verified_service_payment_state","build_verified_payment_context"):
    if name in funcs:
        lo,hi=funcs[name]
        print("TARGET_FN",name,lo,hi)
        for i in range(lo,min(hi,lo+185)+1):
            row=lines[i-1]
            if any(x in row.lower() for x in ("api_key","access_token","password","authorization","secret","token:")):row="[sanitized]"
            print(f"{i:05d} {row[:250]}")
for lo,hi in [(8050,8210),(20770,21070),(27100,27430),(27945,28040)]:
    print("TARGET_RANGE",lo,hi)
    for i in range(lo,hi+1):
        if i>len(lines):break
        row=lines[i-1]
        if any(x in row.lower() for x in ("api_key","access_token","password","authorization","secret","token:")):row="[sanitized]"
        print(f"{i:05d} {row[:220]}")
