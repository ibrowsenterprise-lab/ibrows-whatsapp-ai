"""V133 isolated media tests (Python stdlib; no live credentials or DB)."""
import ast
import hashlib
from pathlib import Path

source = Path("app.py").read_text()
tree = ast.parse(source)
functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
assert 'IBROWS_BUILD_VERSION = "2026-10-08-responsive-media-v133"' in source
assert 'WEB_GALLERY_ADMIN_PREVIEW_MAX_SIDE = 640' in source
routes = [d for fn in tree.body if isinstance(fn, ast.FunctionDef)
          for d in fn.decorator_list if isinstance(d, ast.Call)
          and isinstance(d.func, ast.Attribute) and d.func.attr == "route"]
assert len(routes) == 167, len(routes)

def template(name):
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
for name in ("CONSTRUCTION_PORTFOLIO_TEMPLATE", "SERVICE_PORTFOLIO_TEMPLATE"):
    s = template(name)
    assert "srcset=" in s and "size='640'" in s
    assert "1280w" in s and "640w" in s
monitor = template("MONITORING_TEMPLATE")
assert '<details class="monitor-mobile-menu">' in monitor
assert 'monitor-mobile-menu[open]' in monitor
assert 'aria-label="Admin navigation"' in monitor

class Req:
    method = "GET"
    args = {}
    headers = {}
request = Req()
class Resp:
    def __init__(self, data=b"", status=200, mimetype="application/octet-stream"):
        self.data, self.status_code, self.mimetype = data, status, mimetype
        self.headers = {}
    def set_etag(self, digest):
        self.headers["ETag"] = '"' + digest + '"'
    def make_conditional(self, req):
        return self
class DB:
    def __init__(self, data, mime):
        self.data, self.mime = data, mime
        self.sql, self.args, self.calls = "", (), []
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def cursor(self): return self
    def execute(self, sql, args=()):
        self.sql, self.args = sql, args
        self.calls.append(sql)
    def fetchone(self):
        if "filename,mime_type,sha256,updated_at,byte_size" in self.sql:
            name = "profile.pdf" if self.mime == "application/pdf" else "photo.jpg"
            return name, self.mime, hashlib.sha256(self.data).hexdigest(), None, len(self.data)
        if "substring(file_bytes" in self.sql:
            start, size, _ = self.args
            return (self.data[start-1:start-1+size],)
        if "SELECT file_bytes" in self.sql:
            return (self.data,)
        raise AssertionError(self.sql)

module = ast.Module(body=[functions[name] for name in
    ("_construction_asset_response", "_public_gallery_preview_side", "_parse_single_byte_range")],
    type_ignores=[])
blob = b"%PDF-1.7\\n" + b"X" * (2 * 1024 * 1024)
db = DB(blob, "application/pdf")
ns = dict(
    request=request, Response=Resp, get_db=lambda: db,
    abort=lambda status: (_ for _ in ()).throw(RuntimeError(status)),
    WEB_GALLERY_PREVIEW_MAX_SIDE=1280,
    WEB_GALLERY_MOBILE_PREVIEW_MAX_SIDE=640,
    SERVICE_MEDIA_MAX_RANGE_BYTES=1024*1024,
    _gallery_preview_cache_get=lambda *args: None,
    _gallery_preview_variant=lambda *args: (b"preview", "image/jpeg", "digest"),
    _public_conditional_304=lambda *args: None,
    _construction_safe_filename=lambda name, fallback: name,
    quote=lambda value, safe="": value)
exec(compile(module, "<isolated>", "exec"), ns)
request.method = "HEAD"
r = ns["_construction_asset_response"](1)
assert r.status_code == 200 and len(db.calls) == 1
assert int(r.headers["Content-Length"]) == len(blob)
request.method = "GET"
request.headers = {"Range": "bytes=0-"}
r = ns["_construction_asset_response"](1)
assert r.status_code == 206 and len(r.data) == 1024*1024
assert "substring(file_bytes" in db.calls[-1]
request.headers = {"Range": "bytes=-200"}
r = ns["_construction_asset_response"](1)
assert r.status_code == 206 and r.data == blob[-200:]
request.headers = {"Range": "bytes=999999999-"}
r = ns["_construction_asset_response"](1)
assert r.status_code == 416
request.headers = {"Range": "bytes=0-200", "If-Range": '"wrong"'}
r = ns["_construction_asset_response"](1)
assert r.status_code == 200 and r.data == blob
request.headers = {}
db = DB(b"image-bytes", "image/jpeg")
request.args = {"preview": "1", "size": "640"}
seen = []
ns["get_db"] = lambda: db
ns["_gallery_preview_variant"] = lambda *args: (seen.append(args[-1]) or b"small", "image/jpeg", "hash")
r = ns["_construction_asset_response"](1)
assert r.data == b"small" and seen[-1] == 640
request.args = {"preview": "1", "size": "999999"}
ns["_construction_asset_response"](1)
assert seen[-1] == 1280
assert '"company-profile-2026-pdf", IBROWS_COMPANY_PROFILE_PDF_B64' in source
print("PASS: V133 167 routes, mobile media markup, PDF ranges/HEAD, previews, embedded profile caching")
