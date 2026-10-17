"""Read-only diagnosis of IBROWS security header routing; no POST requests."""
from urllib.request import Request, urlopen
from urllib.error import HTTPError
urls=[
"https://www.ibrowsenterprise.com/",
"https://www.ibrowsenterprise.com/msj?audit_v151=1",
"https://www.ibrowsenterprise.com/msj?garment=Hoodie&audit_v151=1",
"https://ibrows-whatsapp-ai-1.onrender.com/",
"https://ibrows-whatsapp-ai-1.onrender.com/msj?audit_v151=1",
]
for u in urls:
 try:
  req=Request(u,headers={"User-Agent":"IBROWS-security-header-readonly-audit/1.0","Cache-Control":"no-cache","Pragma":"no-cache"})
  with urlopen(req,timeout=35) as r:
   s=r.read(200_000).decode("utf-8","replace")
   h=r.headers
   print("DIAG",u,"status",r.status,
    "final",r.url,"nosniff",repr(h.get("X-Content-Type-Options")),
    "cache",repr(h.get("Cache-Control")),"cf-cache",repr(h.get("CF-Cache-Status")),
    "age",repr(h.get("Age")),"server",repr(h.get("Server")),
    "msj",("Mulungu Si Jemusi" in s),
    "hoodie_out_of_stock",("Hoodies temporarily out of stock" in s),flush=True)
 except Exception as e:
  print("DIAG_ERROR",u,type(e).__name__,str(e)[:180],flush=True)
