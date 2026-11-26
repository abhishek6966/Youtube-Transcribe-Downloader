"""Browser regression: catalog routing, 400 failover, provider errors, no policy bypass."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import shutil, os
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text(); assert html==(ROOT/'Transcript.html').read_text()
marker='        refreshRouteNote();\n        updateStats();\n      })();'
assert marker in html
html=html.replace(marker,'        window.videoTest={ai,state,geminiVideoModels,geminiLinkTranscript,geminiFailureHint,currentTimeline,failCaptions:()=>{getCaptions=()=>Promise.reject(Error("notracks"));}};\n'+marker,1)
mock='''<script>window.requests=[];window.mode='compat';window.fetch=async(url,opts)=>{url=String(url);let body=opts?.body?JSON.parse(opts.body):null;if(url.endsWith('/models'))return Response.json({models:['gemini-3.5-transcribe','gemini-4-hydrogen','gemini-3.8-flash','gemini-3.8-flash-image','gemini-3.6-flash','gemini-3.5-flash-native-audio'].map(x=>({name:'models/'+x,supportedGenerationMethods:['generateContent']}))});if(url.endsWith('/interactions')||url.includes(':generateContent')){let model=body.model||url.split('/').pop().split(':')[0];requests.push({url,body,model});let error=mode==='overload-all'?503:mode==='overload'&&model==='gemini-4-hydrogen'?503:mode==='cooldown'?503:mode==='quota'?429:mode==='denied'?403:mode==='policy'?400:mode==='compat'&&model==='gemini-4-hydrogen'?400:0;if(error)return Response.json({error:{message:mode==='policy'?'copyright restriction <img src=x onerror=alert(1)>':mode==='denied'?'access denied':mode==='quota'?'quota reached':'unsupported request <b>bad</b>'}},{status:error,headers:mode==='cooldown'?{'Retry-After':'60'}:{}});let text=JSON.stringify([{word:'नमस्ते',start:.1,end:.7},{word:'दुनिया',start:.8,end:1.5}]);return Response.json({status:'completed',steps:[{type:'model_output',content:[{type:'text',text}]}]});}return Response.json({});};</script>'''
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox']);p=b.new_page(viewport={'width':1366,'height':768});p.route('**/*',lambda r:r.abort());errors=[];p.on('pageerror',lambda e:errors.append(str(e)));p.on('dialog',lambda d:d.accept())
 p.set_content(html.replace('</head>',mock+'</head>',1),wait_until='domcontentloaded');p.locator('#start-btn').click();p.locator('#api-key').fill('AIza_mock_123456789012345678901234');p.locator('#screen-3.active').wait_for(timeout=12000)
 assert p.locator('#model-select').input_value()=='gemini-4-hydrogen';assert p.evaluate('videoTest.geminiVideoModels(videoTest.ai.models)')==['gemini-4-hydrogen','gemini-3.8-flash','gemini-3.6-flash']
 p.locator('#model-select').select_option('gemini-3.5-transcribe');p.evaluate('videoTest.failCaptions()');p.locator('#url-input').fill('https://youtu.be/6rvUyBiBtik');p.locator('#fetch-btn').click()
 p.wait_for_function('document.querySelector("#transcript").value.includes("नमस्ते") && !document.querySelector("#fetch-btn").disabled',timeout=12000)
 assert p.evaluate('requests.map(r=>r.model)')==['gemini-4-hydrogen','gemini-4-hydrogen','gemini-3.8-flash'];assert p.evaluate('requests[0].body.input[0].uri')=='https://www.youtube.com/watch?v=6rvUyBiBtik';assert p.evaluate('requests[0].body.store') is False;assert p.evaluate('requests[1].body.contents[0].parts[0].fileData.fileUri')=='https://www.youtube.com/watch?v=6rvUyBiBtik';assert p.evaluate('videoTest.currentTimeline().every(w=>w.precision==="estimated")')
 assert 'दुनिया' in p.locator('#transcript').input_value();assert len(p.locator('#transcript-en').input_value().splitlines())==2
 # Overload is recoverable: skip the overloaded model's legacy route and use another model.
 p.evaluate("window.mode='overload';window.requests=[]")
 assert p.evaluate("videoTest.geminiLinkTranscript('6rvUyBiBtik','hi')") is True
 assert p.evaluate('requests.map(r=>r.model)')==['gemini-4-hydrogen','gemini-3.8-flash']
 # All candidates overloaded: exactly four requests, never an unbounded loop.
 result=p.evaluate('''async()=>{window.mode='overload-all';window.requests=[];try{await videoTest.geminiLinkTranscript('6rvUyBiBtik','hi');return null}catch(e){return {count:requests.length,hint:videoTest.geminiFailureHint(e)}}}''')
 assert result['count']==4 and 'HTTP 503' in result['hint'],result
 # Long server-directed cooldown: stop rather than hammering another route.
 result=p.evaluate('''async()=>{window.mode='cooldown';window.requests=[];try{await videoTest.geminiLinkTranscript('6rvUyBiBtik','hi');return null}catch(e){return {count:requests.length,hint:videoTest.geminiFailureHint(e)}}}''')
 assert result['count']==1 and 'HTTP 503' in result['hint'],result
 for mode in ['quota','denied','policy']:
  result=p.evaluate('''async mode=>{window.mode=mode;window.requests=[];try{await videoTest.geminiLinkTranscript('6rvUyBiBtik','hi');return null}catch(e){return {count:requests.length,hint:videoTest.geminiFailureHint(e)}}}''',mode)
  assert result and result['count']==1,result
  if mode=='policy':assert '&lt;img' in result['hint'] and '<img' not in result['hint']
 assert not errors,errors;b.close()
print('Live-catalog mock, audio-only exclusion, HTTP 400 model failover, current and legacy request formats, bilingual result, estimated timings, 503 failover, bounded overload retries, cooldown, quota/access/policy stop, escaped diagnostics passed.')
