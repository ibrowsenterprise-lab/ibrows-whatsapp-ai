"""Diagnostic: print only bounded, relevant source sections, never runtime data."""
from pathlib import Path
import re
text=Path("app.py").read_text()
lines=text.splitlines()
patterns=[
 r"^def admin_design_media_upload\(",
 r"^def _portfolio_media_kind\(",
 r"^def _service_portfolio.*upload",
 r"^def admin_service_portfolio",
 r"SERVICE_PORTFOLIO_MAX_VIDEO_BYTES",
 r"SERVICE_PORTFOLIO_MAX_MEDIA_BATCH_BYTES",
 r"^def _service_portfolio_.*file",
 r"media-upload",
 r"^def .*media.*(upload|sanitize|prepare)",
 r"^def .*_media_(validate|sniff|sanitize)",
 r"^app\.config\[.MAX_CONTENT_LENGTH",
]
matched=[]
for i,line in enumerate(lines):
 if any(re.search(p,line) for p in patterns):
  matched.append(i)
print("SCAN TOTAL LINES",len(lines),"HITS",len(matched))
seen=set()
for idx in matched:
 if "media-upload" in lines[idx] and len(lines[idx])>1500:
  print("MEDIA TEMPLATE",idx+1,lines[idx][:1700])
  continue
 if idx in seen:continue
 pre= max(0,idx-4);post=min(len(lines),idx+18)
 if lines[idx].startswith("def admin_design_media_upload("):
  post=min(len(lines),idx+145)
 if lines[idx].startswith("def _portfolio_media_kind("):
  post=min(len(lines),idx+75)
 print("---- BLOCK",pre+1,post,"----")
 for j in range(pre,post):
  if j in seen:continue
  seen.add(j)
  line=lines[j]
  if len(line)>1100:line=line[:950]+" ... [truncated long template]"
  print(f"{j+1}: {line}")
