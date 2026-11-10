"""Print names only (never values) from public agriculture forms."""
from html.parser import HTMLParser
from urllib.request import urlopen, Request

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.active = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self.active = {'method': a.get('method'), 'action': a.get('action'), 'fields': []}
            self.forms.append(self.active)
        if self.active is not None and tag in ('input','textarea','select'):
            self.active['fields'].append(a.get('name'))
    def handle_endtag(self, tag):
        if tag == 'form':
            self.active = None

for path in ('/agriculture','/agriculture/marketplace'):
    with urlopen(Request('https://www.ibrowsenterprise.com'+path,headers={'User-Agent':'IBROWS-safe-form-inspection/1.0'}),timeout=30) as r:
        html = r.read(1_000_000).decode('utf8','replace')
    p = Parser()
    p.feed(html)
    print(path, p.forms, flush=True)
