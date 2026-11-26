from playwright.sync_api import sync_playwright
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'Transcript.html'
s=p.read_text().replace('        refreshRouteNote();\n        updateStats();\n      })();','        window.testAPI={cleanAudioWords,audioDisagreements,applyAudioChoices,alternateAudioModel,orderedTimeline,entriesFromWords,parseSubtitleText,alignReference,srtTime,romanize,secondBuckets,state,renderEntries,loadVideo,playVideo,startKaraoke,stopKaraoke,buildSrtFile,saneChunk};\n        refreshRouteNote();\n        updateStats();\n      })();',1)
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=__import__('os').environ.get('CHROMIUM_PATH') or __import__('shutil').which('chromium'),headless=True,args=['--no-sandbox'])
 page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/*',lambda r:r.abort())
 page.set_content(s,wait_until='domcontentloaded'); page.wait_for_timeout(250)
 print('page errors:',errors); assert not errors
 print(page.evaluate('''()=>{let a=testAPI;let cue=a.orderedTimeline([{start:43,dur:4,text:'one two three four'},{start:45,dur:3,text:'three four five six'},{start:49,dur:2,text:'five six'}]);return cue.map(x=>x.text)}'''))
 assert page.evaluate('''()=>{let a=testAPI;return a.orderedTimeline([{start:43,dur:4,text:'one two three four'},{start:45,dur:3,text:'three four five six'},{start:49,dur:2,text:'five six'}]).map(x=>x.text).join(' ')}''')=='one two three four five six five six'
 assert page.evaluate('''()=>testAPI.orderedTimeline(testAPI.entriesFromWords([{word:'yes',start:1.01,end:1.2},{word:'yes',start:1.22,end:1.5},{word:'no',start:2.4,end:2.5}])).map(x=>x.text).join(' ')''')=='yes yes no'
 print('VTT:',page.evaluate('''()=>{let a=testAPI;let v='WEBVTT\\n\\n00:00:01.000 --> 00:00:02.000\\n<00:00:01.000><c>one</c> <00:00:01.500><c>two</c>\\n\\n00:00:02.000 --> 00:00:03.000\\none two <00:00:02.000><c>three</c> <00:00:02.500><c>four</c>';return a.orderedTimeline(a.parseSubtitleText(v)).map(x=>[x.text,x.start])}'''))
 assert page.evaluate('''()=>{let a=testAPI;return a.alignReference([{text:'hello',start:0,end:.4,precision:'word'},{text:'world',start:1.2,end:1.5,precision:'word'}],'hello my world').map(x=>[x.text,x.precision])}''')==[['hello','word'],['my','estimated'],['world','word']]
 assert page.evaluate('''()=>testAPI.srtTime(43.267)''')=='00:00:43,267'
 assert page.evaluate('''()=>!testAPI.saneChunk(['one two'],['two one'])&&testAPI.saneChunk(['one two'],['one too'])''')
 assert page.evaluate("""()=>{let a=testAPI;let w=(word,start,end)=>({word,start,end});let p=[w('hello',0,.3),w('world',1,1.3),w('again',2,2.4)],q=[w('hello',0,.3),w('my',.4,.7),w('world',1,1.3),w('again',2,2.4)];let plan=a.audioDisagreements(p,q);return plan.gaps.length===1&&a.applyAudioChoices(plan,{0:'B'}).words.map(x=>x.word).join(' ')==='hello my world again'&&a.applyAudioChoices(plan,{}).words.length===3;}""")
 assert page.evaluate("""()=>{let a=testAPI;let w=(word,start,end)=>({word,start,end});return a.cleanAudioWords([w('yes',1,1.2),w('yes',1,1.2),w('yes',1.3,1.5)]).length===2&&a.alternateAudioModel('groq','whisper-large-v3',['whisper-large-v3','whisper-large-v3-turbo'])==='whisper-large-v3-turbo';}""")
 print('Audio consensus regression checks passed')
 print('Hindi romanization:',page.evaluate('''()=>testAPI.romanize('दिल हाल साल खैरियत')'''))
 page.evaluate('''()=>{let a=testAPI;a.state.videoId='hoNb6HuNmU0';a.state.entries=a.entriesFromWords([{word:'hello',start:1.1,end:1.4},{word:'again',start:1.4,end:1.8},{word:'hello',start:2.1,end:2.4}]);a.renderEntries();window.clock=1.2;window.YT={Player:function(el,options){let mock={playVideo(){},destroy(){},getCurrentTime(){return window.clock},seekTo(t){window.clock=t}};setTimeout(()=>options.events.onReady({target:mock}),0);return mock}};a.startKaraoke();}''')
 page.wait_for_timeout(300)
 print('Karaoke active',page.locator('.karaoke-word.active').all_text_contents());assert page.locator('.karaoke-word.active').all_text_contents()==['hello','hello']
 page.evaluate('window.clock=1.6');page.wait_for_timeout(200);assert page.locator('.karaoke-word.active').all_text_contents()==['again','again']
 page.evaluate('window.clock=1.2');page.wait_for_timeout(200);assert page.locator('.karaoke-word.active').all_text_contents()==['hello','hello']
 page.evaluate('window.clock=8');page.wait_for_timeout(200);assert page.locator('.karaoke-word.active').count()==0
 page.evaluate('testAPI.stopKaraoke()');assert page.locator('.karaoke-scroll').count()==0
 print('SRT:',page.evaluate('testAPI.buildSrtFile(false)'));print('All browser checks passed; runtime errors:',errors);assert not errors
 b.close()
