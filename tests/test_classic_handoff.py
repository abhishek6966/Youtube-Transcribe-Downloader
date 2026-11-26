"""Classic receiver test: sandbox browser blocks real navigation; use an in-memory frame."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import shutil,os
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'Transcript.html').read_text();mock='''<script>window.calls=[];window.fetch=async(url,opts)=>{calls.push([String(url),opts?.headers?.Authorization]);return new Response(JSON.stringify({data:[{id:'gpt-4o-mini'},{id:'whisper-1'}]}),{status:200})}</script>''';html=html.replace('</head>',mock+'</head>',1)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox']);page=b.new_page();page.route("https://**",lambda route:route.abort());page.set_content('<iframe id="classic"></iframe>');page.locator('#classic').evaluate('(e,html)=>e.srcdoc=html',html);frame=page.frame_locator('#classic');frame.locator('#start-btn').wait_for();frame.locator('body').evaluate('''()=>window.dispatchEvent(new MessageEvent('message',{source:parent,origin:location.origin,data:{type:'studio-classic-connect',provider:'openai',key:'sk-proj-mock_1234567890123456'}}))''');frame.locator('#screen-3.active').wait_for(timeout=10000);assert frame.locator('body').evaluate('()=>calls')==[['https://api.openai.com/v1/models','Bearer sk-proj-mock_1234567890123456']];print('Classic receiver, selected provider and automatic transition — passed (in-memory frame)');b.close()
