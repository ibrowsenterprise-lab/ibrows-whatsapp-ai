import ast
import subprocess
from pathlib import Path

def test_existing_application_functions_and_routes_are_preserved():
    old=ast.parse(subprocess.check_output(['git','show','3b2d6038ced3282df570865471ae9068c9a40170:app.py'],text=True))
    new=ast.parse(Path('app.py').read_text())
    def functions(tree):
        return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    before,after=functions(old),functions(new)
    assert before=={key:after[key] for key in before}
