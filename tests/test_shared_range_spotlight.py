"""Shared caption ranges get an explicitly approximate playback schedule, not fabricated exports."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import os, shutil
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text();assert html==(ROOT/'Transcript.html').read_text()
html=html.replace('        refreshRouteNote();\n        updateStats();\n      })();','        window.rangeTest={state,renderEntries,entriesFromWords,wordDisplayBuckets,spotlightSchedule,startKaraoke,stopKaraoke,buildSrtFile};\n        refreshRouteNote();\n        updateStats();\n      })();',1)
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox']);page=b.new_page(viewport={'width':1366,'height':768});page.route('**/*',lambda r:r.abort());errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
 mock='''<script>window.fetch=async u=>new Response(JSON.stringify({data:[{id:'whisper-large-v3'},{id:'whisper-large-v3-turbo'},{id:'llama-3.3-70b-versatile'}]}),{status:200});</script>'''
 page.set_content(html.replace('</head>',mock+'</head>',1),wait_until='domcontentloaded');page.locator('#start-btn').click();page.locator('#api-key').fill('gsk_mock_12345678901234567890123');page.locator('#screen-3.active').wait_for(timeout=12000)
 # Synthetic shared ranges using the timestamp pattern from the screenshot, with a later timed anchor.
 result=page.evaluate('''()=>{let a=rangeTest;a.state.videoId='fixture';a.state.entries=[{start:27.599,dur:5.11,text:'जय श्री राम जय जय श्री राम राम',wt:Array(8).fill(27.599),timingBlocked:true,cueStart:27.599,cueEnd:32.709},...a.entriesFromWords([{word:'आगे',start:29.119,end:29.4},{word:'चलो',start:30.72,end:31}]),{start:33,dur:.08,text:'one two three four',timingBlocked:true,cueStart:33,cueEnd:33.08},{start:35,dur:2,text:'مرحبا كيف حالك',timingBlocked:true,cueStart:35,cueEnd:37}];a.renderEntries();let rows=a.wordDisplayBuckets(),before=a.buildSrtFile(false),schedule=a.spotlightSchedule(rows);window.clock=27.65;window.YT={Player:function(el,options){let mock={playVideo(){},destroy(){},getCurrentTime(){return window.clock},seekTo(t){window.clock=t}};setTimeout(()=>options.events.onReady({target:mock}),0);return mock}};a.startKaraoke();return {rows,schedule,before,after:a.buildSrtFile(false)}}''')
 assert result['before']==result['after'];assert all(x['unresolved'] for x in result['rows'][:8]);assert len(result['schedule'])==17
 assert all(x['b']['fallback'] for x in result['schedule'][:8]);assert abs(result['schedule'][0]['b']['sec']-27.599)<1e-6;assert abs(result['schedule'][7]['b']['end']-29.119)<1e-6
 assert result['schedule'][8]['b']['sec']==29.119 and not result['schedule'][8]['b'].get('fallback');assert result['schedule'][10:14]==[None]*4
 page.wait_for_function("document.querySelectorAll('.karaoke-word.active').length===2")
 for i in range(8):
  slot=result['schedule'][i]['b'];page.evaluate('(t)=>window.clock=t',(slot['sec']+slot['end'])/2)
  page.wait_for_function('(i)=>Array.from(document.querySelectorAll(\'.karaoke-word.active\')).map(n=>Number(n.dataset.wordIndex)).join()===`${i},${i}`',arg=i)
  assert 'Approximate spotlight' in page.locator('#timing-now').inner_text()
  assert page.locator('.karaoke-word.active.unresolved').count()==2
  assert page.locator('.karaoke-word.active').first.evaluate('e=>getComputedStyle(e).color')=='rgb(255, 255, 255)'
 # Preserve the true timed anchor and instrumental gap. Backward seek recovers correct fallback word.
 page.evaluate('window.clock=29.2');page.wait_for_function("document.querySelector('.karaoke-word.active')?.dataset.wordIndex==='8'")
 page.evaluate('window.clock=32');page.wait_for_function("document.querySelectorAll('.karaoke-word.active').length===0")
 page.evaluate('window.clock=33.04');page.wait_for_timeout(120);assert page.locator('.karaoke-word.active').count()==0;assert 'Caption range only' in page.locator('#timing-now').inner_text()
 page.evaluate('window.clock=36.1');page.wait_for_function("document.querySelector('.karaoke-word.active')?.dataset.wordIndex==='15'")
 # Clicking a dotted word seeks to its own estimated position, not the shared range start.
 page.locator('#transcript-karaoke [data-word-index="3"].karaoke-word').evaluate('e=>e.click()');page.wait_for_function("document.querySelector('.karaoke-word.active')?.dataset.wordIndex==='3'")
 assert abs(page.evaluate('window.clock')-result['schedule'][3]['b']['sec'])<1e-6
 page.wait_for_timeout(350);page.screenshot(path='/mnt/data/classic-shared-range-spotlight-preview.png',animations='disabled')
 assert not errs,errs;b.close()
print('Eight shared-range words highlighted in sequence, paired scripts, white active text, true anchors, too-short snapshots, silence, Arabic range, backward seek, click-to-seek and unchanged SRT passed.')
