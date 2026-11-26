"""Real Chromium and WAV decoding, deterministic ASR fixture (not a live lyric test)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import os,shutil,io,wave,json
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text()
assert html==(ROOT/'Transcript.html').read_text()
html=html.replace('        refreshRouteNote();\n        updateStats();\n      })();','        window.classicTest={repairSequence,orderedTimeline,entriesFromWords,cleanAudioWords,audioResultWords,reconcileAudio,parseSubtitleText,currentTimeline,state,renderEntries};\n        refreshRouteNote();\n        updateStats();\n      })();',1)
phrase='तुम्हारे तस्वीर के सहारे मौसम कई गुजारे'.split()
# Deliberately corrupted timestamp observations. The test checks source order, not song accuracy.
ws=[dict(word=w,start=a,end=a+.22) for w,a in zip(phrase,[.1,.65,.85,1.05,.4,1.45,1.8])]
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox']);page=b.new_page(viewport={'width':1366,'height':850});errors=[];calls=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  u=r.request.url
  if u=='https://classic.test/':r.fulfill(status=200,content_type='text/html',body=html)
  elif 'api.groq.com' in u:
   calls.append(u)
   if u.endswith('/models'):d={'data':[{'id':'whisper-large-v3'},{'id':'whisper-large-v3-turbo'}]}
   elif '/audio/transcriptions' in u:d={'words':ws,'segments':[{'start':0,'end':2.2,'text':' '.join(phrase)}],'language':'hi'}
   else:d={'choices':[{'message':{'content':'{}'}}]}
   r.fulfill(status=200,content_type='application/json',headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body=json.dumps(d))
  elif 'api.deepgram.com' in u:
   d={'projects':[{'project_id':'mock'}]} if u.endswith('/projects') else {'stt':[{'name':'nova-3','batch':True}]}
   r.fulfill(status=200,content_type='application/json',headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body=json.dumps(d))
  else:r.abort()
 mock="""<script>window.mockCalls=[];window.fetch=async function(url,opts){url=String(url);mockCalls.push(url);let d;if(url.endsWith('/models'))d={data:[{id:'whisper-large-v3'},{id:'whisper-large-v3-turbo'}]};else if(url.includes('/audio/transcriptions'))d={words:FIXTURE,segments:[{start:0,end:2.2,text:PHRASE}],language:'hi'};else d={choices:[{message:{content:'{}'}}]};return new Response(JSON.stringify(d),{status:200});};</script>""".replace('FIXTURE',json.dumps(ws,ensure_ascii=False)).replace('PHRASE',json.dumps(' '.join(phrase),ensure_ascii=False))
 page.route('**/*',lambda r:r.abort());page.set_content(html.replace('</head>',mock+'</head>',1),wait_until='domcontentloaded');page.wait_for_timeout(100)
 out=page.evaluate('w=>classicTest.orderedTimeline(classicTest.entriesFromWords(w)).map(x=>({text:x.text,start:x.start,end:x.end,precision:x.precision}))',ws)
 assert [x['text'] for x in out]==phrase and all(a['start']<b['start'] for a,b in zip(out,out[1:])) and any(x['precision']=='estimated' for x in out),out
 # Same-time cue offsets must not interleave with later cue, nor erase genuine repetitions.
 out=page.evaluate('()=>classicTest.orderedTimeline([{start:0,dur:2,text:"first second third",wt:[0,0,1.2]},{start:1.5,dur:1,text:"fourth fourth",wt:[1.5,1.9]}]).map(w=>w.text)');assert out==['first','second','third','fourth','fourth'],out
 assert page.evaluate('''()=>classicTest.audioResultWords({words:[{word:'one',start:0,end:.2},{word:'three',start:.5,end:.7},{word:'two',start:.3,end:.5}],segments:[{text:'one two three'}]}).map(w=>w.word)''')==['one','two','three']
 assert page.evaluate('''async()=>{let w=(word,start,end)=>({word,start,end}),a=[w('middle',1,1.2)],b=[w('first',.2,.5),w('middle',1,1.2),w('last',2,2.2)];let x=await classicTest.reconcileAudio(a,b,b);return x.words.map(w=>w.word)}''')==['first','middle','last']
 assert page.evaluate('''async()=>{let w=(word,start,end)=>({word,start,end}),a=[w('one',0,.2),w('three',.8,1)],b=[w('one',0,.2),w('two',.4,.6),w('three',.8,1)];return (await classicTest.reconcileAudio(a,b,[])).words.map(w=>w.word)}''')==['one','three']
 page.screenshot(path='/tmp/classic-welcome.png');page.locator('#start-btn').click();page.locator('#screen-2.active').wait_for();page.screenshot(path='/tmp/classic-connect.png');page.locator('#api-key').fill('gsk_mock_12345678901234567890123');page.locator('#screen-3.active').wait_for(timeout=12000)
 page.locator('#accuracy-level').select_option('maximum')
 stream=io.BytesIO()
 with wave.open(stream,'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b'\0\0'*16000*3)
 page.locator('#audio-input').set_input_files({'name':'test.wav','mimeType':'audio/wav','buffer':stream.getvalue()});page.wait_for_function('document.getElementById("transcript").value.includes("गुजारे")',timeout=25000)
 assert page.evaluate('()=>classicTest.currentTimeline().map(w=>w.text)')==phrase
 assert page.evaluate("mockCalls.filter(x=>x.includes('/audio/transcriptions')).length")==3,page.evaluate('mockCalls')
 assert page.locator('#audit-btn').is_visible()
 assert 'estimated' in page.locator('#timing-quality').inner_text().lower()
 assert page.evaluate('document.documentElement.scrollHeight<=innerHeight && document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path='/tmp/classic-workspace.png');page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors;print('Classic: timestamp collisions, reversed provider times, sequence reconciliation, corroborated boundaries, real WAV decode, three mocked audio passes, audit and responsive viewport — passed');b.close()
