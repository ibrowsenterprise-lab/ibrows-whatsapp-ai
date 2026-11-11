import ast
from pathlib import Path
s=Path('app.py').read_text('utf-8').splitlines()
t=ast.parse('\n'.join(s))
for x in t.body:
 if isinstance(x,ast.FunctionDef) and x.name in ('canonicalize_service','get_verified_service_payment_state'):
  print('FUNCTION',x.name,x.lineno,x.end_lineno)
  for i in range(x.lineno,x.end_lineno+1):
   print(f'{i}: '+s[i-1][:220])
