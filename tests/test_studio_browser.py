"""Browser UI E2E with mocked provider outputs, real WAV decoding and playback."""
from playwright.sync_api import sync_playwright
from pathlib import Path
import io, wave, json, shutil, os
ROOT=Path(__file__).resolve().parents[1]
buf=io.BytesIO()
with wave.open(buf,'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b'\x00\x00'*16000*3)
media=buf.getvalue()
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'],headless=True)
 page=b.new_page(accept_downloads=True,viewport={'width':1280,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 mock="""window.fetch=async (url,opts)=>{if(String(url).endsWith('/models'))return new Response(JSON.stringify({data:[{id:'whisper-large-v3'},{id:'whisper-large-v3-turbo'},{id:'llama-test'}]}),{status:200});if(String(url).includes('api.groq.com'))return new Response(JSON.stringify({language:'en',words:[{word:'hello',start:.1,end:.7},{word:'yes',start:1,end:1.3},{word:'yes',start:1.4,end:1.8}],segments:[]}),{status:200});throw Error('unexpected request')}"""
 html=(ROOT/'index.html').read_text().replace('<link rel="stylesheet" href="studio.css">','<style>'+(ROOT/'studio.css').read_text()+'</style>').replace('<script src="studio.js" defer></script>','<script>'+mock+'</script><script>'+(ROOT/'studio.js').read_text()+'</script>')
 page.set_content(html);page.wait_for_function("document.getElementById('environment').textContent.includes('browser workspace')")
 page.locator('#welcomeStart').click();page.locator('#apiKey').fill('gsk_test_key_1234567890');page.wait_for_selector('#screen-3',state='visible');assert page.locator('#modelCount').inner_text()=='Groq · 3 models discovered';page.locator('#fileTab').click();page.locator('#media').set_input_files({'name':'test.wav','mimeType':'audio/wav','buffer':media});page.locator('#start').click();page.wait_for_function("!document.getElementById('showQuality').disabled",timeout=30000);page.locator('#advancedTools').click();page.locator('#showQuality').click()
 assert page.locator('.word').count()==6;assert page.locator('#metrics').inner_text().find('100.0%')>=0;assert page.locator('#metrics').inner_text().find('3\nCorroborated words')>=0
 page.locator('[data-close=quality]').click();page.locator('.word[data-i="0"]').first.click();page.wait_for_selector('#editRow',state='visible');page.locator('#editWord').fill('Hello');page.locator('#saveEdit').click();assert page.locator('.word[data-i="0"]').first.inner_text()=='Hello';page.locator('#undoEdit').click();assert page.locator('.word[data-i="0"]').first.inner_text()=='hello'
 page.locator('[data-close=review]').click();page.evaluate("document.getElementById('player').pause();document.getElementById('player').currentTime=1.1");page.wait_for_timeout(350);assert page.locator('.word.active').count()==2
 page.locator('#advancedTools').click()
 with page.expect_download() as download:page.locator('#json').click()
 page.locator('[data-close=advancedDrawer]').click()
 d=json.loads(Path(download.value.path()).read_text());assert d['report']['accuracy'] is None and 'gsk_test_key_1234567890' not in json.dumps(d)
 page.screenshot(path='/tmp/studio-desktop.png');page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/studio-mobile.png');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors;print('Studio browser: cloud mock requests, real WAV decode, dual-pass comparison, edit/undo, playback, audit export, responsive layout — passed');b.close()
