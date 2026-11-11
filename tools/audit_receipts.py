from pathlib import Path
s=Path("app.py").read_text("utf-8").splitlines()
for lo,hi in [(1600,1615),(5445,5476),(28721,28787)]:
 print("RANGE",lo,hi)
 for i in range(lo,hi+1):
  row=s[i-1]
  if any(k in row.lower() for k in ("api_key","password","access_token","authorization","secret","bearer")):row="[omitted]"
  print(f"{i:05d} {row[:230]}")
