"""Extract current production Project Discovery JS for direct Node regression."""
import ast
from pathlib import Path

tree=ast.parse(Path("app.py").read_text(encoding="utf-8"))
for node in tree.body:
    if isinstance(node,ast.Assign) and any(
       isinstance(t,ast.Name) and t.id=="PROJECT_DISCOVERY_UI_JS" for t in node.targets):
        script=ast.literal_eval(node.value)
        break
else:
    raise AssertionError("Project Discovery UI JavaScript was not found")
assert "syncAI" in script and "ai-details" in script
p=Path("/tmp/ibrows_v139_discovery_ui.js")
p.write_text(script,encoding="utf-8")
print("Extracted actual production Project Discovery JS",len(script),"bytes")
