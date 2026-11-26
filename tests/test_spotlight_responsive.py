"""Shared per-word rows, real browser layout, simulated clock. No live song accuracy claim."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import os,shutil
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text();assert html==(ROOT/'Transcript.html').read_text()
html=html.replace('        refreshRouteNote();\n        updateStats();\n      })();','        window.spotTest={state,renderEntries,entriesFromWords,currentTimeline,wordDisplayBuckets,startKaraoke,stopKaraoke};\n        refreshRouteNote();\n        updateStats();\n      })();',1)
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox']);page=b.new_page(viewport={'width':1366,'height':768});page.route('**/*',lambda r:r.abort());errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
 mock='''<script>window.fetch=async u=>new Response(JSON.stringify({data:[{id:'whisper-large-v3'},{id:'whisper-large-v3-turbo'},{id:'llama-3.3-70b-versatile'}]}),{status:200});</script>'''
 page.set_content(html.replace('</head>',mock+'</head>',1),wait_until='domcontentloaded');page.locator('#start-btn').click();page.locator('#api-key').fill('gsk_mock_12345678901234567890123');page.locator('#screen-3.active').wait_for(timeout=12000)
 page.evaluate('''()=>{const a=spotTest;a.state.videoId='fixture';a.state.entries=[...a.entriesFromWords(Array.from({length:28},(_,i)=>({word:i%2?'अंतरराष्ट्रीयकरण':'मौसम',start:i*.7,end:i*.7+.4}))),{start:20,dur:.08,text:'जय जय राम जय राम',wt:[20,20,20,20,20]},...a.entriesFromWords([{word:'आगे',start:21,end:21.5},{word:'चलो',start:22,end:22.5}])];a.renderEntries();window.clock=21.2;window.YT={Player:function(el,options){let mock={playVideo(){},destroy(){},getCurrentTime(){return window.clock},seekTo(t){window.clock=t}};setTimeout(()=>options.events.onReady({target:mock}),0);return mock}};a.startKaraoke()}''')
 page.wait_for_function("document.querySelectorAll('.karaoke-word.active').length===2");page.wait_for_timeout(350)
 assert page.locator('.karaoke-line').count()==70
 assert page.locator('.karaoke-word.active').all_text_contents()==['आगे','aage'],page.locator('.karaoke-word.active').all_text_contents()
 def shared():
  v=page.evaluate('''()=>{let a=document.querySelector('#transcript-karaoke'),b=document.querySelector('#transcript-en-karaoke');return [a.scrollTop,b.scrollTop,...[a,b].map(x=>{let n=x.querySelector('.active');let r=n.getBoundingClientRect(),z=x.getBoundingClientRect();return {visible:r.top>=z.top-1&&r.bottom<=z.bottom+1,index:n.dataset.wordIndex};})]}''')
  assert abs(v[0]-v[1])<=2 and v[2]['visible'] and v[3]['visible'] and v[2]['index']==v[3]['index'],v
 shared()
 page.evaluate('window.clock=20.03');page.wait_for_timeout(120);assert page.locator('.karaoke-word.active').count()==0 and page.locator('.karaoke-word.unresolved').count()==10;assert 'Caption range only' in page.locator('#timing-now').inner_text()
 page.evaluate('window.clock=2.25');page.wait_for_timeout(200);shared()
 page.locator('#tab-english').click();page.wait_for_timeout(120);page.locator('#tab-side').click();page.wait_for_timeout(250);shared()
 for w,h in [(1920,1080),(1775,850),(1366,768),(1183,573),(1024,600),(768,1024),(390,844),(320,568),(844,390)]:
  page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(150)
  assert page.evaluate('document.documentElement.scrollHeight<=innerHeight && document.documentElement.scrollWidth<=innerWidth')
  for sel in ['#back-2','#screen-3 .studio','#screen-3 .panel:first-child','#screen-3 .panel:last-child']:
   r=page.locator(sel).bounding_box();assert r and r['x']>=-1 and r['y']>=-1 and r['x']+r['width']<=w+1 and r['y']+r['height']<=h+1,(w,h,sel,r)
  for sel in ['#fetch-btn','#audio-btn','#dl-both','#dl-srt','#polish-btn','#clear-btn']:
   page.locator(sel).scroll_into_view_if_needed();r=page.locator(sel).bounding_box();assert r and r['x']>=-1 and r['y']>=-1 and r['x']+r['width']<=w+1 and r['y']+r['height']<=h+1,(w,h,sel,r)
  if (w,h)==(1366,768):
   page.evaluate("document.querySelectorAll('#screen-3 .panel').forEach(p=>p.scrollTop=0)");page.wait_for_timeout(100);page.screenshot(path='/mnt/data/classic-compact-spotlight-preview.png',animations='disabled')
  print(f'{w}x{h}: fixed frame, controls reachable',flush=True)
 assert not errs,errs;b.close()
print('Word rows, repeated unresolved words, same active row, paired scroll, tab changes and viewport checks passed.')
