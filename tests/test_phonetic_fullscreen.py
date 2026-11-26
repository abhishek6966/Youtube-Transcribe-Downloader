"""Context proposals cannot change words without two fresh matching timed observations."""
from pathlib import Path
import sys, os, shutil, json, io, wave
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import universal_engine as e
# Synthetic phrase, not actual song timing.
def word(t,a,b,source='A'):return dict(text=t,word=t,start=a,end=b,precision='word',source=source)
base=[word('है',.5,.8),word('दे',1,1.3),word('मेरा',1.5,1.9)]
alt=[word('है',.5,.8,'B'),word('तय',1,1.3,'B'),word('मेरा',1.5,1.9,'B')]
alt2=[dict(w,source='C') for w in alt]
cs=e.phonetic_candidates([{'i':1,'word':'tay'},{'i':1,'word':'तय'},{'i':0,'word':'bad'}],base);assert len(cs)==1 and cs[0]['candidate']=='तय'
assert not e.corroborate_phonetic(base,cs[0],[alt]);assert not e.corroborate_phonetic(base,cs[0],[alt,alt]);assert base[1]['text']=='दे'
assert e.corroborate_phonetic(base,cs[0],[alt,alt2]) and base[1]['text']=='तय'
assert len(e.vocabulary_hint('x'*200))==180
html=(ROOT/'index.html').read_text();assert html==(ROOT/'Transcript.html').read_text()
html=html.replace('        refreshRouteNote();\n        updateStats();\n      })();','        window.phoneticTest={parsePhoneticCandidates,corroboratePhonetic,scanPhonetic,ai,state,currentTimeline,renderEntries,entriesFromWords,startProcessing,stopProcessing};\n        refreshRouteNote();\n        updateStats();\n      })();',1)
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox']);page=b.new_page(viewport={'width':1920,'height':1080});page.route('**/*',lambda r:r.abort());errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
 fixture=[dict(w,word=w['text']) for w in [word('है',.5,.8),word('दे',1,1.3),word('मेरा',1.5,1.9)]]
 mock='''<script>window.calls=[];window.fetch=async(url,opts)=>{url=String(url);let d;if(url.endsWith('/models'))d={data:[{id:'whisper-large-v3'},{id:'whisper-large-v3-turbo'},{id:'llama-3.3-70b-versatile'}]};else if(url.includes('/audio/transcriptions')){calls.push({model:opts.body.get('model'),hint:opts.body.get('prompt')});d={language:'hi',words:calls.length>3?ALT:BASE,segments:[]};}else if(url.includes('/chat/completions'))d={choices:[{message:{content:'[{"i":1,"word":"तय"}]'}}]};else d={};return new Response(JSON.stringify(d),{status:200})};</script>'''.replace('ALT',json.dumps(alt,ensure_ascii=False)).replace('BASE',json.dumps(fixture,ensure_ascii=False))
 page.set_content(html.replace('</head>',mock+'</head>',1),wait_until='domcontentloaded')
 # Initial landing retains max width. Third screen fills viewport.
 assert page.locator('.app').bounding_box()['width']<1200
 page.locator('#start-btn').click();page.locator('#screen-2.active').wait_for();page.locator('#api-key').fill('gsk_mock_12345678901234567890123');page.locator('#screen-3.active').wait_for(timeout=12000)
 page.locator('#accuracy-level').select_option('maximum');page.locator('#pronunciation-btn').click();page.locator('#pronunciation-vocab').fill('तय');page.get_by_role('button',name='Done',exact=True).click()
 # Exercise real WAV decode, 3 initial ASR calls, 2 recropped unprompted calls, 1 guided audit pass.
 data=io.BytesIO()
 with wave.open(data,'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b'\0\0'*16000*4)
 page.locator('#audio-input').set_input_files({'name':'fixture.wav','mimeType':'audio/wav','buffer':data.getvalue()})
 page.wait_for_function('!document.getElementById("audio-btn").disabled && document.getElementById("transcript").value.includes("तय")',timeout=25000)
 assert page.evaluate('phoneticTest.currentTimeline().map(w=>w.text)')==['है','तय','मेरा'];calls=page.evaluate('calls');assert len(calls)==6 and [c['hint'] for c in calls]==[None]*5+['तय'],calls
 for size in [(1920,1080),(1366,768),(390,844)]:
  page.set_viewport_size(dict(width=size[0],height=size[1]));page.wait_for_timeout(150)
  assert page.locator('.app').bounding_box()['width']>=size[0]-1
  assert page.evaluate('document.documentElement.scrollHeight<=innerHeight && document.documentElement.scrollWidth<=innerWidth')
  assert page.locator('#tx-view').bounding_box()['height']>=64
  if size==(1920,1080):page.screenshot(path='/mnt/data/classic-fullscreen-preview.png')
 assert not errs,errs;b.close()
print('Phonetic candidate validation, two fresh audio rechecks, optional hint isolation, full-viewport layout and original landing width passed.')
