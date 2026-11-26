import unittest, sys, tempfile, wave, json, math, struct, pathlib
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import universal_engine as e
import universal_server as s

def w(text,start,end,source):return dict(text=text,start=start,end=end,source=source,precision='word',confidence=.9,language='en',speaker=None)
class Tests(unittest.TestCase):
    def test_overlap_and_repetition(self):
        a=e.clean([dict(word='yes',start=1,end=1.2),dict(word='yes',start=1,end=1.2),dict(word='yes',start=1.3,end=1.5)],3,'A')
        self.assertEqual([x['text'] for x in a],['yes','yes'])
    def test_boundary_missing(self):
        a=[w('middle',1,1.4,'A')];b=[w('first',.1,.4,'B'),w('middle',1,1.4,'B'),w('last',2,2.3,'B')];c=[w('first',.11,.41,'C'),w('middle',1.02,1.4,'C'),w('last',2.01,2.3,'C')]
        result,issues=e.reconcile([a,b,c]);self.assertEqual([x['text'] for x in result],['first','middle','last']);self.assertEqual(len(issues),0);self.assertEqual(result[0]['correction'],'recovered omitted word')
        result,issues=e.reconcile([a,b]);self.assertEqual(len(issues),2);self.assertEqual(len(result),1)
    def test_substitution(self):
        a=[w('misheard',1,1.5,'A')];b=[w('correct',1.02,1.5,'B')];c=[w('correct',1.03,1.5,'C')];r,_=e.reconcile([a,b,c]);self.assertEqual(r[0]['text'],'correct');self.assertEqual(r[0]['review'],'review');self.assertEqual(len(r[0]['observations']),3)
    def test_benchmark(self):
        import benchmark
        a=[w("one",0,.2,"human"),w("two",.3,.5,"human"),w("three",.6,.8,"human")]
        b=[w("one",.1,.3,"ASR"),w("wrong",.3,.5,"ASR")]
        q=benchmark.compare(a,b);self.assertEqual(q["substitutions"],1);self.assertEqual(q["deletions"],1);self.assertAlmostEqual(q["error_rate"],2/3);self.assertAlmostEqual(q["mean_start_error_ms"],100)
    def test_no_guarantee(self):
        a=[w('word',1,1.3,'A')];r,_=e.reconcile([a]);q=e.quality(r,[],3,3,['A'],[],'hash','fast');self.assertIsNone(q['accuracy']);self.assertEqual(q['single_pass'],1)
    def test_chunks(self):
        for d in [1,30,35,36,60,65,90,91,140]:
            chunks=list(e.windows(d));self.assertAlmostEqual(sum(hi-lo for a,b,lo,hi in chunks),d);self.assertTrue(all(x[3]==y[2] for x,y in zip(chunks,chunks[1:])))
    def test_url_validation(self):
        self.assertEqual(s.youtube_id('https://youtu.be/hoNb6HuNmU0'),'hoNb6HuNmU0')
        for x in ['http://youtu.be/hoNb6HuNmU0','https://youtu.be.evil.com/hoNb6HuNmU0','https://localhost/hoNb6HuNmU0','https://youtube.com@evil.com/watch?v=hoNb6HuNmU0']:
            with self.assertRaises(ValueError):s.youtube_id(x)
    def test_full_engine_fake_providers(self):
        # Genuine audio decoding/cutting; deterministic mock ASR, not a live accuracy test.
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'source.wav'
            with wave.open(str(path),'wb') as f:
                f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b'\x00\x00'*16000*36)
            calls=[]
            def groq(p,key,model,lang):
                calls.append(model);return ([{'word':'hello','start':.1,'end':.5}], 'en', [])
            def dg(p,key,lang):return ([{'word':'hello','start':.12,'end':.55}], 'en', [])
            opts=dict(mode='advanced',groq='secret-groq',deepgram='secret-dg',local=False,cache=True)
            with patch.object(e,'groq',groq),patch.object(e,'deepgram',dg):
                res=e.run(path,opts,cache_dir=td);self.assertEqual(res['report']['coverage'],100);self.assertEqual(res['report']['corroborated'],1);self.assertNotIn('secret-',json.dumps(res));first=len(calls)
                res2=e.run(path,opts,cache_dir=td);self.assertEqual(len(calls),first);self.assertEqual(res['words'],res2['words']);self.assertEqual(res2['report']['coverage'],100)
            self.assertEqual(len(list(pathlib.Path(td).rglob('*.json'))),2)
if __name__=='__main__':unittest.main()
