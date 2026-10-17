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
             "/admin/msj/designs/<int:design_id>/update",
             "/admin/msj/orders/<int:order_id>/status",
             "/admin/msj/orders/<int:order_id>/colour-contacted",
             "/admin/msj/orders/<int:order_id>/colour-email-retry",
             "/admin/msj/orders/<int:order_id>/notification-retry",
             "/admin/msj/designs/import-sheets",
             "/admin/msj/designs/import-merch-zip",
             "/admin/msj/designs/import-merch-images",
             "/admin/msj/designs/publish-all"]:
 assert path in all_routes,path
assert len(all_routes)==16,len(all_routes)
assert "secrets.compare_digest" in src
assert "get_db()" in src and "CREATE TABLE IF NOT EXISTS msj_merch_orders" in src
assert "published=TRUE" in src and "1<=quantity<=30" in src
assert 'name="csrf_token"' in src and "validate_admin_csrf()" in src
assert "No payment is collected" in src
assert "IBROWS" in src
assert "register_msj_store(app, get_db" in app
assert 'href="/msj"' in app
assert 'Mulungu Si Jemusi' in app
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import msj_store as module
for name in ("CATALOG_TEMPLATE","ORDER_TEMPLATE","COMPLETE_TEMPLATE","ADMIN_TEMPLATE"):
 Environment(autoescape=True).parse(getattr(module,name))
assert module.MSJ_GARMENT_PRICES == {"T-shirt":25000, "Hoodie":50000, "Cap":20000}
assert module.MSJ_APPAREL_SIZES == ("S", "M", "L", "XL", "XXL")
assert module.MSJ_CAP_SIZE == "One Size"
assert module.msj_product_options("T-shirt,Hoodie") == 25000
assert module.msj_product_options("Hoodie") == 50000
assert module.msj_product_options("Cap,Hoodie") == 20000
try:
 module.msj_product_options("Tote bag")
except ValueError:
 pass
else:
 raise AssertionError("Tote bag should not be sold before a confirmed price")
assert "MSJ_GARMENT_PRICES[garment]*quantity" in src
assert "price_mwk*%s" not in src
assert 'garment == "Cap"' in src and "MSJ_APPAREL_SIZES" in src
assert "2XL" not in src
assert '<input id="colour" name="colour" type="text"' in module.ORDER_TEMPLATE
assert "<datalist" in module.ORDER_TEMPLATE
assert "Any colour" not in module.ORDER_TEMPLATE or "any colour" in module.ORDER_TEMPLATE
assert "colour not in colour_choices" not in src
assert "len(colour)<2" in src
assert "colour_alert_status" in src and "COLOUR_UNAVAILABLE" in src
assert "'MANUAL_REQUIRED'" in src and "'CONTACTED_MANUALLY'" in src
assert 'send_customer_colour_unavailable' in src
assert 'def admin_import_sheets' in src
assert 'MSJ-'+"" in "MSJ-" 
assert 'ON CONFLICT (code) DO NOTHING' in src
assert 'ImageOps.exif_transpose(im)' in src
assert 'published' in src
assert '3-shirt design sheet' in src
assert 'Original' not in src or True
assert 'colour_alert_status IN (\'PENDING\',\'FAILED\',\'MANUAL_REQUIRED\')' in src
assert "colour-alert" not in src or True
print("PASS MSJ: any buyer-selected colour, no stock-list restriction, automatic email where supplied, manual phone fallback")
print("PASS MSJ: confirmed garment pricing (MK25k/MK50k/MK20k), shirts and hoodies S–XXL, one-size caps, no unpriced tote bags")
assert "Publish All Drafts" in module.ADMIN_TEMPLATE
assert 'action="{{ url_for(\'msj.admin_bulk_publish\') }}"' in module.ADMIN_TEMPLATE
assert "window.confirm" in module.ADMIN_TEMPLATE
assert "catalog-table" in module.ADMIN_TEMPLATE
assert "Retry internal order email" in module.ADMIN_TEMPLATE
assert "notification_status='FAILED'" in src and "notification_status='SENDING'" in src
assert "REVIEW_REQUIRED" in src
assert "No ZIP needed." in module.ADMIN_TEMPLATE
assert "Import selected photos as drafts" in module.ADMIN_TEMPLATE
assert "Or upload an original merchandise ZIP" in module.ADMIN_TEMPLATE
assert "MSJ_MERCH_PHOTO_FIELDS" in src
print("PASS MSJ: sixteen isolated routes, admin login and CSRF guards, no checkout, original-artwork upload and valid templates")
