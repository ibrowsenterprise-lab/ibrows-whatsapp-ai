"""Lightweight integration regression checks. No secrets or network calls."""
from pathlib import Path
import ast
s=Path("app.py").read_text(encoding="utf-8")
ast.parse(s, filename="app.py")
assert 'IBROWS_BUILD_VERSION = "2026-10-09-readmalawi-community-v137"' in s
assert s.count('id="community-project"') == 1
assert s.count('readmalawi-library.onrender.com') == 3
assert 'ReadMalawi is a separate, digital-first reading community' in s
assert 'ReadMalawi is not yet a registered NGO' in s
assert 'website does not accept donations or payments' in s
assert '<strong>{{ team_members|length }} people</strong>' in s
assert 'repeat(8,minmax(92px,1fr))' in s
assert '"name":"Fatuma Nyirenda","role":"IT Specialist Lead"' in s
assert '<strong>7 people</strong>' not in s
for must_have in ('@app.route("/company-profile.pdf"', '@app.route("/project-discovery"',
                  '@app.route("/pricing"', '@app.route("/admin/login"',
                  "WHATSAPP INTEGRITY", "IBROWS_COMPANY_PROFILE_PDF_B64"):
    assert must_have in s, must_have
print("PASS: V137 ReadMalawi links, disclaimers, staff, and route integrity")
