"""Real browser WAV decode and playback, simulated ASR and direct Gemini responses."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import os, shutil, io, wave
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text();assert html==(ROOT/'Transcript.html').read_text()
html=html.replace('        refreshRouteNote();\n        updateStats();\n      })();','        window.liveTest={state,ai,showNoCaptionFallback,geminiFailureHint,retryGeminiLink,parseGeminiLinkWords,geminiLinkTranscript,currentTimeline,guardProgressivePlayback,session:()=>progressiveSession,failCaptions:()=>{getCaptions=()=>Promise.reject(Error("notracks"));}};\n        refreshRouteNote();\n        updateStats();\n      })();',1)
mock='''<script>window.calls=0;window.releaseChunk=null;window.fetch=async(url,opts)=>{url=String(url);let d;if(url.endsWith('/models'))d={data:[{id:'whisper-large-v3'},{id:'whisper-large-v3-turbo'},{id:'llama-3.3-70b-versatile'}]};else if(url.includes('/audio/transcriptions')){calls++;if(calls===2)await new Promise(r=>window.releaseChunk=r);d={language:'hi',words:[{word:calls===1?'नमस्ते':'दुनिया',start:calls===1?.1:3,end:calls===1?1:4}],segments:[]};}else if(url.includes(':generateContent')){window.direct=JSON.parse(opts.body);if(window.failGemini)return new Response("{}",{status:429});d={candidates:[{finishReason:'STOP',content:{parts:[{text:JSON.stringify([{word:'hello',start:0.2,end:0.8},{word:'world',start:1,end:1.5}])}]}}]};}else d={};return new Response(JSON.stringify(d),{status:200})};</script>'''
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox','--autoplay-policy=no-user-gesture-required']);page=b.new_page(viewport={'width':1366,'height':768});page.route('**/*',lambda r:r.abort());errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(html.replace('</head>',mock+'</head>',1),wait_until='domcontentloaded');page.locator('#start-btn').click();page.locator('#api-key').fill('gsk_mock_12345678901234567890123');page.locator('#screen-3.active').wait_for(timeout=12000)
 page.evaluate('liveTest.failCaptions()');page.locator('#url-input').fill('https://youtu.be/abcdefghijk');page.locator('#fetch-btn').click();page.locator('#no-caption-audio').wait_for(timeout=10000);assert page.locator('#no-caption-gemini').is_visible()
 page.locator('#accuracy-level').select_option('fast');data=io.BytesIO()
 with wave.open(data,'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b'\0\0'*16000*36)
 page.locator('#audio-input').set_input_files({'name':'fixture.wav','mimeType':'audio/wav','buffer':data.getvalue()})
 page.wait_for_function('window.releaseChunk!==null && document.querySelector("#transcript").value.includes("नमस्ते")',timeout=25000)
 assert page.locator('#audio-btn').is_disabled();assert len(page.locator('#transcript-en').input_value())>10;assert 'दुनिया' not in page.locator('#transcript').input_value()
 page.wait_for_selector('#local-audio-player');page.wait_for_selector('#transcript-karaoke');page.evaluate('document.querySelector("#local-audio-player").currentTime=35; liveTest.guardProgressivePlayback(document.querySelector("#local-audio-player"))');assert page.evaluate('document.querySelector("#local-audio-player").currentTime')<=32.51
 page.evaluate('releaseChunk()');page.wait_for_function('!document.querySelector("#audio-btn").disabled && document.querySelector("#transcript").value.includes("दुनिया")',timeout=20000)
 assert page.evaluate('liveTest.currentTimeline().map(w=>w.text)')==['नमस्ते','दुनिया'];assert len(page.locator('#transcript-en').input_value().splitlines())==2;assert page.evaluate('liveTest.session()===null')
 # Gemini direct link receives URL, not extracted audio. Model timestamps explicitly estimated.
 page.evaluate('''async()=>{let t=liveTest;t.state.videoId='abcdefghijk';t.ai.provider={type:'gemini',base:'https://generativelanguage.googleapis.com/v1beta'};t.ai.key='mock';t.ai.audioModel='gemini-test';await t.geminiLinkTranscript('abcdefghijk','en')}''')
 assert page.evaluate('direct.contents[0].parts[0].fileData.fileUri')=='https://www.youtube.com/watch?v=abcdefghijk';assert page.evaluate('liveTest.currentTimeline().every(w=>w.precision==="estimated")')
 page.evaluate("window.failGemini=true;liveTest.showNoCaptionFallback()")
 page.on('dialog',lambda d:d.accept())
 page.locator('#no-caption-gemini').click()
 page.wait_for_function('document.querySelector(".fallback-detail")?.textContent.includes("HTTP 429")')
 assert page.locator('#fetch-btn').is_enabled()
 page.evaluate('window.failGemini=false')
 page.locator('#no-caption-gemini').click()
 page.wait_for_function('document.querySelector("#transcript").value.includes("hello") && !document.querySelector("#fetch-btn").disabled')
 assert not errors,errors;b.close()
print('Progressive first chunk before second completes, synchronized original/romanized results, authorized media playback frontier, final sequence, no-caption action, and estimated Gemini link route passed.')
