"""Regression for caption phrase collisions and actual playback clock (mocked player).
No network or song-specific correction. The fixtures are synthetic timings.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
import shutil, os, sys, subprocess, tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import universal_engine as engine
html=(ROOT/'index.html').read_text()
assert html==(ROOT/'Transcript.html').read_text()
html=html.replace('        refreshRouteNote();\n        updateStats();\n      })();','        window.timingTest={orderedTimeline,entriesFromWords,parseSubtitleText,refineBlockedTiming,secondBuckets,splitStamp,state,renderEntries,currentTimeline,buildSrtFile,startKaraoke,stopKaraoke};\n        refreshRouteNote();\n        updateStats();\n      })();',1)
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox']);page=b.new_page(viewport={'width':1366,'height':850});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.route('**/*',lambda r:r.abort());page.set_content(html,wait_until='domcontentloaded')
 # All offsets at the same cue start; real cue span permits a labelled estimate.
 cue=dict(start=99,dur=4,text='one two three four five six seven eight',wt=[99]*8)
 out=page.evaluate('c=>timingTest.orderedTimeline([c])',cue)
 assert [x['start'] for x in out]==[99+i*.5 for i in range(8)] and all(x['precision']=='estimated' for x in out)
 # Same phrase, one short display frame. Preserve the text; do not pretend to know the timings.
 cue['dur']=.08
 out=page.evaluate('c=>{let a=timingTest;a.state.entries=[c,...a.entriesFromWords([{word:"next",start:99.2,end:99.7}])];a.renderEntries();return {words:a.currentTimeline(),text:document.getElementById("transcript").value,srt:a.buildSrtFile(false)}}',cue)
 assert all(x['timingBlocked'] for x in out['words'][:8]) and out['words'][-1]['start']==99.2,out
 assert '[~01:39.000–01:39.080] one two three four five six seven eight' in out['text'],out
 assert '00:01:39,000 --> 00:01:39,080' in out['srt'] and '00:01:39,200 --> 00:01:39,700' in out['srt']
 # A coarse cue's inferred timing must not shift a genuine later word anchor.
 out=page.evaluate('''()=>timingTest.orderedTimeline([{start:99,dur:4,text:'one two three four five six seven eight'},{start:100,dur:.5,text:'next',wt:[100],we:[100.5],precision:'word'}])''')
 assert out[-1]['start']==100 and all(x.get('timingBlocked') for x in out[:-1]),out
 # Very short rolling display snapshot followed by the same actual timed sequence.
 vtt='WEBVTT\n\n00:00:01.000 --> 00:00:01.010\nhello again\n\n00:00:01.010 --> 00:00:02.000\n<00:00:01.010>hello <00:00:01.500>again\n\n00:00:03.000 --> 00:00:04.000\n<00:00:03.000>hello <00:00:03.500>again'
 out=page.evaluate('v=>timingTest.orderedTimeline(timingTest.parseSubtitleText(v))',vtt)
 assert [x['text'] for x in out]==['hello','again','hello','again'] and abs(out[0]['start']-1.01)<.001,out
 # Mixed prefix and explicit VTT words: prefix has no usable interval; timed suffix remains valid.
 vtt='WEBVTT\n\n00:00:10.000 --> 00:00:12.000\na long untimed display <00:00:10.000>hello <00:00:11.000>world'
 out=page.evaluate('v=>timingTest.orderedTimeline(timingTest.parseSubtitleText(v))',vtt)
 # The zero-width prefix shares the first offset with the explicit word; it must not be presented as accurate.
 assert all(x.get('timingBlocked') for x in out[:4]) and out[-2]['start']==10 and not out[-2].get('timingBlocked') and out[-1]['start']==11,out
 # Multi-script timing: preserve text without treating a phrase as a single verified word.
 for text in ['आज मौसम अच्छा है','مرحبا كيف حالك','你好世界今天很好','วันนี้อากาศดีมาก','今日はいい天気です']:
  out=page.evaluate('t=>timingTest.orderedTimeline([{start:10,dur:.03,text:t}])',text)
  assert len(out)>1 and all(x.get('timingBlocked') for x in out),out
  assert ''.join(x['text'] for x in out)==''.join(text.split()),out
 # Normal fast, independently supplied timestamps are not arbitrarily suppressed.
 out=page.evaluate('''()=>timingTest.orderedTimeline(timingTest.entriesFromWords([{word:'a',start:1,end:1.07},{word:'b',start:1.08,end:1.14}]))''')
 assert all(not x.get('timingBlocked') for x in out),out
 # Two audio passes with matching sequence can recover blocked positions; one pass cannot.
 out=page.evaluate("""()=>{let a=timingTest,p=a.orderedTimeline([{start:10,dur:.03,text:'one two three'}]),q=[{word:'one',start:10,end:10.3,precision:'word'},{word:'two',start:10.3,end:10.6,precision:'word'},{word:'three',start:10.6,end:10.9,precision:'word'}];return [a.refineBlockedTiming(p,[q]).changed,a.refineBlockedTiming(p,[q,q]).changed]}""")
 assert out==[0,3],out
 # TXT millisecond/range round-trip.
 out=page.evaluate('''()=>{let a=timingTest;let p=a.splitStamp('[~01:39.000–01:39.080] a b');return [p.sec,p.end,p.text,p.estimated]}''');assert out==[99,99.08,'a b',True],out
 # Actual player clock, unresolved gap, seek back and forth; same active word in each column.
 page.evaluate('''()=>{let a=timingTest;a.state.videoId='fixture';a.state.entries=[{start:99,dur:.08,text:'one two three four five six seven eight',wt:[99,99,99,99,99,99,99,99]},...a.entriesFromWords([{word:'next',start:99.2,end:99.7},{word:'after',start:101,end:101.5}])];a.renderEntries();window.clock=99.04;window.YT={Player:function(el,options){let mock={playVideo(){},destroy(){},getCurrentTime(){return window.clock},seekTo(t){window.clock=t}};setTimeout(()=>options.events.onReady({target:mock}),0);return mock}};a.startKaraoke()}''')
 page.wait_for_timeout(300);assert page.locator('.karaoke-word.active').count()==0
 page.evaluate('window.clock=99.4');page.wait_for_timeout(150);assert page.locator('.karaoke-word.active').all_text_contents()==['next','next']
 page.evaluate('window.clock=100');page.wait_for_timeout(150);assert page.locator('.karaoke-word.active').count()==0
 page.evaluate('window.clock=101.2');page.wait_for_timeout(150);assert page.locator('.karaoke-word.active').all_text_contents()==['after','after']
 page.evaluate('window.clock=99.4');page.wait_for_timeout(150);assert page.locator('.karaoke-word.active').all_text_contents()==['next','next']
 assert not errors,errors;b.close()
# Local engine compressed multiword input and valid following anchor.
a=engine.clean([dict(word='one two three four five',start=99,end=99.08),dict(word='next',start=99.2,end=99.7)],110)
assert all(w.get('timingBlocked') for w in a[:-1]) and a[-1]['start']==99.2,a
# Worker JSON3 shared offsets retain cue duration, not an artificial word timestamp.
if shutil.which('node'):
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'worker.mjs';p.write_text((ROOT/'worker/worker.js').read_text());subprocess.run(['node','--input-type=module','-e',f'''import {{captionEvents}} from '{p.as_uri()}';import assert from 'node:assert/strict';let [c]=captionEvents([{{tStartMs:99000,dDurationMs:4000,segs:[{{utf8:'one two three',tOffsetMs:0}},{{utf8:' four',tOffsetMs:2000}}]}}]);assert.deepEqual(c.wt,[99,99,99,101]);assert.deepEqual(c.we,[101,101,101,103]);assert.equal(c.precision,'estimated');'''],check=True)
print('Dense phrase, rolling snapshots, multi-script timing, precise fast words, millisecond export, seek/silence, local engine and worker fixtures passed.')
