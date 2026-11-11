from pathlib import Path
import ast
s=Path('app.py').read_text('utf-8').splitlines()
t=ast.parse('\n'.join(s))
for lo,hi in [(40,180),(7855,7870),(1580,1682),(21949,21993),(5908,5961),(19753,19829)]:
 print('SOURCE',lo,hi)
 for i in range(lo,hi+1):
  row=s[i-1]
  if any(w in row.lower() for w in ('secret','password','access_token','api_key','authorization','bearer ','token =')):row='[sanitized]'
  print(f'{i:05d} {row[:180]}')
for n in t.body:
 if isinstance(n,ast.FunctionDef) and 'whatsapp_service_window' in n.name:
  print('SERVICE_WINDOW_FN',n.name,n.lineno,n.end_lineno)
  for i in range(n.lineno,min(n.end_lineno,n.lineno+75)+1):
   row=s[i-1]
   if any(w in row.lower() for w in ('secret','password','access_token','api_key','authorization')):row='[sanitized]'
   print(f'{i:05d} {row[:180]}')
