"""Real HTTP loopback integration, with mocked ASR execution."""
import json, sys, pathlib, threading, urllib.request, urllib.error, time, unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server, universal_server as studio
from http.server import ThreadingHTTPServer
class ServiceTests(unittest.TestCase):
    def test_loopback(self):
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(http.server_port)
        def get(path,body=None,headers=None):
            r=urllib.request.Request(url+path,data=body,headers={'Host':'127.0.0.1:8765',**(headers or {})});return urllib.request.urlopen(r,timeout=10)
        def fake(path,opts,progress,cache_dir=None,partial=lambda *a:None):
            self.assertEqual(pathlib.Path(path).read_bytes(),b'test audio');self.assertEqual(opts['groq'],'not-a-real-key');progress('Mock ASR',50);partial([{'text':'hello','start':.1,'end':.4}],1,2);time.sleep(.45);return {'words':[],'report':{'accuracy':None}}
        try:
            with get('/') as r:self.assertIn(b'YouTube Transcribe Downloader',r.read())
            with get('/Transcript.html') as r:self.assertIn(b'repairSequence',r.read())
            with get('/studio-api/capabilities') as r:self.assertIn('local_whisper',json.load(r))
            with self.assertRaises(urllib.error.HTTPError) as er:get('/studio-api/capabilities',headers={'Origin':'https://evil.example'})
            self.assertEqual(er.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError):get('/studio-api/capabilities',headers={'Host':'evil.example'})
            with patch.object(studio.engine,'run',fake):
                with get('/studio-api/create',json.dumps({'groq':'not-a-real-key','local':False}).encode(),{'Content-Type':'application/json'}) as r:jid=json.load(r)['id']
                with get('/studio-api/upload?id='+jid,b'test audio') as r:self.assertEqual(json.load(r)['id'],jid)
                saw_partial=False
                for _ in range(30):
                    with get('/studio-api/job?id='+jid) as r:raw=r.read();job=json.loads(raw)
                    self.assertNotIn(b'not-a-real-key',raw)
                    if job.get('partial'):
                        self.assertEqual(job['partial']['words'][0]['text'],'hello');self.assertEqual(job['partial']['frontier'],1);saw_partial=True
                    if job['status']=='done':break
                    time.sleep(.1)
                self.assertEqual(job['status'],'done');self.assertTrue(saw_partial)
        finally:http.shutdown();http.server_close();thread.join();studio.JOBS.clear()
if __name__=='__main__':unittest.main()
