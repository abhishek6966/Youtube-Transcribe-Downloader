"""Real browser geometry checks for the welcome and connection pages."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import os,shutil
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text()
assert html==(ROOT/'Transcript.html').read_text()
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
    page=b.new_page();page.route('**/*',lambda r:r.abort()); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    def fixed(sel):
        r=page.locator(sel).bounding_box();assert r and r['width']>0 and r['height']>0 and r['x']>=-1 and r['y']>=-1 and r['x']+r['width']<=page.viewport_size['width']+1 and r['y']+r['height']<=page.viewport_size['height']+1,(sel,r,page.viewport_size)
        assert page.locator(sel).evaluate('el=>{let r=el.getBoundingClientRect(),t=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return el.contains(t)}'),sel
    def no_document_overflow():
        assert page.evaluate('document.documentElement.scrollHeight<=innerHeight && document.documentElement.scrollWidth<=innerWidth')
    for w,h in [(1920,1080),(1366,768),(1280,720),(1024,600),(768,1024),(390,844),(360,640),(320,568),(844,390),(390,360)]:
        page.set_viewport_size({'width':w,'height':h});page.set_content(html,wait_until='domcontentloaded')
        no_document_overflow();fixed('#start-btn');fixed('#info-btn')
        assert page.locator('.demo-card').is_visible()
        if (w,h) in [(1366,768),(390,844)]:page.screenshot(path=f'/mnt/data/responsive-welcome-{w}.png',animations='disabled')
        page.locator('#start-btn').click();page.locator('#screen-2.active').wait_for()
        no_document_overflow();fixed('#back-1');fixed('#to-step3')
        for el in ['#way1-card','#way2-card','#api-key','#provider-choice','#worker-url']:
            page.locator(el).scroll_into_view_if_needed();fixed(el)
        # Expanded optional panel and error message cannot hide navigation.
        page.locator('#way1-panel details summary').click();page.locator('#dg-key').scroll_into_view_if_needed();fixed('#dg-key');fixed('#back-1');fixed('#to-step3')
        page.locator('#way1-panel details summary').click();page.locator('.choose-content').evaluate('el=>el.scrollTop=0')
        if (w,h) in [(1366,768),(390,844)]:page.screenshot(path=f'/mnt/data/responsive-connect-{w}.png',animations='disabled')
        page.locator('#way2-card').click();fixed('#to-step3');page.locator('#to-step3').click();page.locator('#screen-3.active').wait_for();no_document_overflow()
        page.locator('#back-2').click();page.locator('#screen-2.active').wait_for();fixed('#back-1');page.locator('#back-1').click();fixed('#start-btn')
        print(f'{w}x{h}: all navigation and input reachability passed',flush=True)
    assert not errors,errors;b.close()
