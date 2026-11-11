from pathlib import Path
s=Path('app.py').read_text('utf-8').splitlines()
for lo,hi in [(6064,6124),(7870,7950),(19832,19870),(14688,14736)]:
 print('RANGE',lo,hi)
 for i in range(lo,hi+1):
  row=s[i-1]
  if any(w in row.lower() for w in ['secret','api_key','password','access_token','authorization','brevo_api_key']):row='[omitted]'
  print(f'{i:05d}: {row[:210]}')
