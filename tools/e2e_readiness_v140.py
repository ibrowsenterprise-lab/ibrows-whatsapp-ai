#!/usr/bin/env python3
"""Review code-level live E2E safety without loading the application or using data."""
import ast
from pathlib import Path
s=Path('app.py').read_text()
t=ast.parse(s)
need=('_create_website_service_request','_render_service_request_page',
      '_public_service_common_fields','validate_public_service_csrf',
      'get_public_service_csrf','business_registration_service',
      'send_website_service_request_alert_email',
      'send_service_request_alert_email',
      '_service_request_send_notifications')
matches=[]
for n in t.body:
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
    if n.name in need or ('service_request' in n.name and ('create' in n.name or 'alert' in n.name or 'email' in n.name)):
      matches.append(n)
for n in matches:
  code=ast.get_source_segment(s,n) or ''
  # Specific business-side hooks and validation only, never print secrets/ENV values
  print('\n'+'='*15+' FUNCTION '+n.name+' line='+str(n.lineno)+' '+'='*15)
  print(code[:9500])
print('FUNCTIONS_END',len(matches))
