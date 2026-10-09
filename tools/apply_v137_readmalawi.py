"""Apply the ReadMalawi / IBROWS cross-site integration to the current V136 app.
This changes only the public IBROWS homepage HTML and style; all backoffice
payments, WhatsApp, client records and project-discovery routes stay untouched.
"""
from pathlib import Path

SOURCE = Path("app.py")
source = SOURCE.read_text(encoding="utf-8")
original = source

def replace_once(label, old, new):
    global source
    count = source.count(old)
    if count == 0 and new in source:
        print(f"ALREADY APPLIED: {label}")
        return
    if count != 1:
        raise AssertionError(f"{label}: expected one anchor, found {count}")
    source = source.replace(old, new)
    print(f"PATCHED: {label}")

replace_once("Build version",
    'IBROWS_BUILD_VERSION = "2026-10-09-fatuma-team-v136"',
    'IBROWS_BUILD_VERSION = "2026-10-09-readmalawi-community-v137"')

replace_once("8 team members in grid",
    ".team-mini-row { display:grid; grid-template-columns:repeat(7,minmax(92px,1fr));",
    ".team-mini-row { display:grid; grid-template-columns:repeat(8,minmax(92px,1fr));")

replace_once("Community showcase CSS",
    "    .contact { background:var(--soft); }",
    """    .community-project { background:#f7faf8; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }
    .community-project-inner { display:grid; grid-template-columns:1.2fr .8fr; gap:30px; align-items:center; }
    .community-project p { color:var(--muted); max-width:740px; }
    .community-project-side { padding:24px; border:1px solid var(--line); border-radius:18px; background:#fff; }
    .community-project-side strong { color:var(--brand); font-size:18px; }
    .community-project-side p { font-size:14px; margin:10px 0 0; }
    @media(max-width:820px){.community-project-inner{grid-template-columns:1fr}}
    .contact { background:var(--soft); }""")

replace_once("Homepage navigation",
    """        <a href="/company-profile">Company Profile</a>
        <a href="#assistant">AI Assistant</a>""",
    """        <a href="/company-profile">Company Profile</a>
        <a href="#community-project">Community</a>
        <a href="#assistant">AI Assistant</a>""")

replace_once("ReadMalawi showcase",
    """  <section class="profile-strip">
    <div class="wrap profile-strip-grid">""",
    """  <section id="community-project" class="community-project" aria-labelledby="readmalawi-title">
    <div class="wrap community-project-inner">
      <div>
        <span class="eyebrow">Community initiative</span>
        <h2 id="readmalawi-title">ReadMalawi — make room for reading</h2>
        <p>ReadMalawi is a separate, digital-first reading community founded by Jones Nalikungwi. Its work so far is sharing digital books through an existing WhatsApp community of 126 members. The proposed physical book-donation programme is a future ambition, not an activity already completed.</p>
        <div class="actions">
          <a class="btn btn-primary" href="https://readmalawi-library.onrender.com/" target="_blank" rel="noopener noreferrer">Explore ReadMalawi</a>
          <a class="btn btn-secondary" href="https://readmalawi-library.onrender.com/library.html" target="_blank" rel="noopener noreferrer">Visit the reading library</a>
        </div>
      </div>
      <aside class="community-project-side" aria-label="ReadMalawi status">
        <strong>Independent and community-led</strong>
        <p>Discover legal reading resources, learning prompts and local-language learning plans. ReadMalawi is not yet a registered NGO, and its website does not accept donations or payments.</p>
      </aside>
    </div>
  </section>

  <section class="profile-strip">
    <div class="wrap profile-strip-grid">""")

replace_once("Live team count",
    "<strong>7 people</strong><span>Leadership and core team shown</span>",
    "<strong>{{ team_members|length }} people</strong><span>Leadership and core team shown</span>")

replace_once("Homepage footer",
    """      <a href="/team">Team</a>
      <a href="/company-profile">Company Profile</a>
      <a href="/privacy">Privacy Policy</a>""",
    """      <a href="/team">Team</a>
      <a href="/company-profile">Company Profile</a>
      <a href="https://readmalawi-library.onrender.com/" target="_blank" rel="noopener noreferrer">ReadMalawi</a>
      <a href="/privacy">Privacy Policy</a>""")

assert "Fatuma Nyirenda" in source and "IBROWS_COMPANY_PROFILE_PDF_B64" in source
assert "/project-discovery" in source and "WHATSAPP INTEGRITY" in source
assert source.count('id="community-project"') == 1
assert source.count("readmalawi-library.onrender.com") == 3
if source != original:
    SOURCE.write_text(source, encoding="utf-8")
print("ReadMalawi homepage integration OK")
