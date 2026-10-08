"""V132 privacy and regression smoke tests, stdlib only."""
import ast, re, secrets
from pathlib import Path

src = Path("app.py").read_text()
assert 'IBROWS_BUILD_VERSION = "' in src
assert 'WEB_GALLERY_ADMIN_PREVIEW_MAX_SIDE = 640' in src
assert 'PRICING INTEGRITY V126 READY' in src
assert 'validate_csrf()' in src
tree = ast.parse(src)
routes = [d for f in tree.body if isinstance(f, ast.FunctionDef)
          for d in f.decorator_list if isinstance(d, ast.Call)
          and isinstance(d.func, ast.Attribute) and d.func.attr == "route"]
assert len(routes) == 167, len(routes)

fn = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "add_security_headers")
fn.decorator_list = []
compiled = compile(ast.Module(body=[fn], type_ignores=[]), "<privacy-test>", "exec")
class Request:
    method, host, endpoint = "GET", "www.ibrowsenterprise.com", "public_test"
    def __init__(self, path): self.path = path
class Response:
    mimetype, status_code, is_streamed = "application/pdf", 200, False
    def __init__(self): self.headers = {}
    def get_data(self, as_text=False): return ""
    def set_data(self, data): pass

cases = [
    ("/quotation/token", True), ("/quotation/token/pdf", True),
    ("/quotation/token/deposit-invoice.pdf", True),
    ("/project-status/token", True), ("/project-status/token/invoice/DEPOSIT.pdf", True),
    ("/project-discovery/token/step/3", True), ("/project-discovery/token/complete", True),
    ("/admin/leads", True), ("/project-discovery", False),
    ("/project-discovery/ui.js", False), ("/cleaning-services", False), ("/", False)
]
for path, private in cases:
    ns = dict(request=Request(path), session={}, re=re, secrets=secrets,
              IBROWS_PUBLIC_BASE_URL="https://www.ibrowsenterprise.com",
              _admin_success_feedback_message=lambda response: "",
              _admin_html_already_has_feedback=lambda html, msg: False,
              _admin_feedback_banner_html=lambda msg: msg)
    exec(compiled, ns)
    headers = ns["add_security_headers"](Response()).headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    if private:
        assert headers.get("X-Robots-Tag") == "noindex, nofollow, noarchive", path
        assert "no-store" in headers["Cache-Control"], path
        assert "Link" not in headers, path
    else:
        assert 'rel="canonical"' in headers.get("Link", ""), path
        assert "no-store" not in headers.get("Cache-Control", ""), path

admin_js = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "admin_confirm_actions_js")
script = next(v.value.value for v in admin_js.body if isinstance(v, ast.Assign)
              if any(isinstance(t, ast.Name) and t.id == "script" for t in v.targets))
assert "installPortfolioSaveHints()" in script
assert "form.addEventListener('input', markUnsaved)" in script
assert "form.addEventListener('change', markUnsaved)" in script
Path("/tmp/ibrows-v132-admin.js").write_text(script)
print("PASS: 167 routes unchanged, 12 private/public response cases and mobile form hints")
