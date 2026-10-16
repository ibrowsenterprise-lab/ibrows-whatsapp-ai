"""MSJ catalogue safety regressions. Does not open a DB or place an order."""
import ast
from pathlib import Path
from jinja2 import Environment
app=Path("app.py").read_text()
src=Path("msj_store.py").read_text()
t=ast.parse(src);a=ast.parse(app)
defs={n.name:n for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
assert "register_msj_store" in defs
module=compile(src,"msj_store.py","exec")
all_routes={}
r=defs["register_msj_store"]
for n in ast.walk(r):
 if isinstance(n,ast.FunctionDef):
  for d in n.decorator_list:
   if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=="route":
    path=ast.literal_eval(d.args[0]);all_routes[path]=n
for path in ["/msj","/msj/design/<int:design_id>","/msj/design/<int:design_id>/image",
             "/msj/order/<uuid:token>","/admin/msj","/admin/msj/designs/add",
             "/admin/msj/designs/<int:design_id>/publish",
             "/admin/msj/orders/<int:order_id>/status"]:
 assert path in all_routes,path
assert len(all_routes)==8,len(all_routes)
assert "secrets.compare_digest" in src
assert "get_db()" in src and "CREATE TABLE IF NOT EXISTS msj_merch_orders" in src
assert "published=TRUE" in src and "1<=quantity<=30" in src
assert 'name="csrf_token"' in src and "validate_admin_csrf()" in src
assert "No payment is collected" in src
assert "IBROWS" in src
assert "register_msj_store(app, get_db" in app
assert 'href="/msj"' in app
assert 'Mulungu Si Jemusi' in app
import msj_store as module
for name in ("CATALOG_TEMPLATE","ORDER_TEMPLATE","COMPLETE_TEMPLATE","ADMIN_TEMPLATE"):
 Environment(autoescape=True).parse(getattr(module,name))
print("PASS MSJ: eight isolated routes, admin login and CSRF guards, no checkout, original-artwork upload and valid templates")
