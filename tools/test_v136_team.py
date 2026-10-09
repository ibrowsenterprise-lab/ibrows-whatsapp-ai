"""V136 staff roster and portrait regression checks without live CRM credentials."""
import ast
import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

source = Path("app.py").read_text()
tree = ast.parse(source)
assignments={}
functions={}
for node in tree.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name):
                assignments[target.id] = node.value
    if isinstance(node,ast.FunctionDef):
        functions[node.name] = node

assert ast.literal_eval(assignments["IBROWS_BUILD_VERSION"]) in {
    "2026-10-09-fatuma-team-v136",
    "2026-10-09-readmalawi-community-v137",
    "2026-10-09-profile-team-integration-v138",
}
team=ast.literal_eval(assignments["PUBLIC_TEAM_MEMBERS"])
assets=ast.literal_eval(assignments["PUBLIC_TEAM_IMAGE_B64"])
assert len(team)==8
assert len(assets)==8
original={"jones-nalikungwi","martha-nalikungwi","sylvester-katopola",
          "christopher-ngalu","amos-mngoli","lewis-tambala","kumbukani-mkandawire"}
assert original.issubset({p["slug"] for p in team})
staff=[member for member in team if member["slug"]=="fatuma-nyirenda"]
assert len(staff)==1
assert staff[0]["name"]=="Fatuma Nyirenda"
assert staff[0]["role"]=="IT Specialist Lead"
assert all(m["slug"] in assets for m in team)

jpeg=base64.b64decode(assets["fatuma-nyirenda"],validate=True)
assert jpeg[:3]==b"\xff\xd8\xff" and jpeg[-2:]==b"\xff\xd9"
assert len(jpeg)>6000
assert source.count('"slug":"fatuma-nyirenda"')==1
assert 'TEAM V136 READY: Fatuma Nyirenda IT Specialist Lead, image=embedded' in source

routes=[d for f in tree.body if isinstance(f,ast.FunctionDef)
        for d in f.decorator_list if isinstance(d,ast.Call)
        and isinstance(d.func,ast.Attribute) and d.func.attr=="route"]
assert len(routes)==168
fn=functions["public_team_photo"]
fn.decorator_list=[]
lookups=[]
ns={"PUBLIC_TEAM_IMAGE_B64":assets,
    "_embedded_asset_response":lambda key,data,mime:(lookups.append((key,mime)) or (data,mime)),
    "abort":lambda status: (_ for _ in ()).throw(RuntimeError(status))}
exec(compile(ast.Module(body=[fn],type_ignores=[]),"<public-team>", "exec"),ns)
data,mime=ns["public_team_photo"]("fatuma-nyirenda")
assert mime=="image/jpeg" and base64.b64decode(data)==jpeg
assert lookups==[("team:fatuma-nyirenda","image/jpeg")]
try:
    ns["public_team_photo"]("not-a-person")
    raise AssertionError("Missing team photo not rejected")
except RuntimeError as ex:
    assert str(ex)=="404"

home=ast.literal_eval(assignments["PUBLIC_WEBSITE_TEMPLATE"])
team_html=ast.literal_eval(assignments["TEAM_PAGE_TEMPLATE"])
assert "team_members" in home and 'member.slug' in home
assert "team_members" in team_html and 'member.slug' in team_html
# Route count checked before isolated photo-handler decorator removal.
for marker in ("BUSINESS EMAIL V134 READY","CLIENT PRIVACY V132 READY",
               "TYPOGRAPHY V135 READY", "PRICING INTEGRITY V126 READY"):
    assert marker in source
print("PASS: Eight staff, exact Fatuma role, all prior staff retained, image/jpeg decoded and served, 168 routes unchanged")
