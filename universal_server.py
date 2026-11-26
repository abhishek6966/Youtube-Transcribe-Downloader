"""Loopback-only studio endpoints; no keys stored on disk."""
import json, os, re, threading, tempfile, shutil, time, uuid, urllib.parse, pathlib
import universal_engine as engine
JOBS={}; LOCK=threading.Lock(); MAX_UPLOAD=512*1024*1024
CACHE=pathlib.Path(__file__).resolve().parent/'.studio-cache'

def youtube_id(url):
    p=urllib.parse.urlparse(url);host=(p.hostname or '').lower()
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):raise ValueError('Use an HTTPS YouTube link.')
    if host=='youtu.be':v=p.path.strip('/')
    elif host in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'):
        v=(urllib.parse.parse_qs(p.query).get('v') or [''])[0] if p.path=='/watch' else (p.path.split('/')[-1] if p.path.startswith(('/shorts/','/embed/','/live/')) else '')
    else:v=''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',v):raise ValueError('Invalid YouTube video link.')
    return v

def read_json(h):
    n=int(h.headers.get('Content-Length','0'))
    if not 0<n<=256*1024:raise ValueError('Invalid settings size.')
    return json.loads(h.rfile.read(n))

def settings(d):
    mode=d.get('mode','advanced');lang=d.get('language','')
    if mode not in ('fast','advanced','maximum'):raise ValueError('Invalid mode.')
    if lang and not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2,4})?',lang):raise ValueError('Invalid language code.')
    result={'mode':mode,'language':lang,'local':bool(d.get('local',True)),'cache':bool(d.get('cache',False)),'context':bool(d.get('context',False)),'reference':str(d.get('reference',''))[:100000]}
    for k in ('groq','deepgram'):
        v=str(d.get(k,'')).strip()
        if len(v)>512 or any(c in v for c in '\r\n'):raise ValueError('Invalid API key.')
        result[k]=v
    return result

def execute(job,source,opts,remote=False):
    try:
        def progress(status,n):job.update(status='running',stage=status,progress=n)
        with tempfile.TemporaryDirectory() as td:
            if remote:
                import yt_dlp
                progress('Acquiring authorized audio',1)
                url='https://www.youtube.com/watch?v='+source
                def check(info,*,incomplete=False):
                    if info.get('duration') and info['duration']>engine.MAX_SECONDS:return 'Video exceeds four-hour limit'
                with yt_dlp.YoutubeDL({'format':'bestaudio/best','outtmpl':os.path.join(td,'audio.%(ext)s'),'noplaylist':True,'quiet':True,'max_filesize':MAX_UPLOAD,'match_filter':check,'socket_timeout':30}) as y:
                    y.extract_info(url,download=True)
                files=[p for p in pathlib.Path(td).glob('audio.*') if p.is_file() and p.suffix not in ('.part','.ytdl')]
                if not files:raise RuntimeError('Audio unavailable; use an authorized local file or caption workflow.')
                source=files[0]
            result=engine.run(source,opts,progress,cache_dir=CACHE)
            job.update(status='done',stage='Complete',progress=100,result=result)
    except Exception as e:
        # No provider response bodies, credentials or arbitrary URL details in client errors.
        msg=str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__
        job.update(status='error',stage='Processing stopped',error=msg[:400])
    finally:
        if not remote:
            try:os.unlink(source)
            except OSError:pass
        opts.clear()

def dispatch(h,path,method):
    if not path.startswith('/studio-api/'):return False
    try:
        if method=='GET' and path=='/studio-api/capabilities':h._send(engine.capabilities());return True
        if method=='GET' and path=='/studio-api/job':
            q=urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query); j=JOBS.get((q.get('id') or [''])[0]);h._send({k:v for k,v in j.items() if k not in ('opts','created')} if j else {'error':'Unknown job'},200 if j else 404);return True
        if method=='POST' and path=='/studio-api/create':
            d=read_json(h);opts=settings(d);link=str(d.get('url','')).strip();video=None
            if link:
                if not d.get('authorized'):raise ValueError('Confirm that you have permission to process this audio.')
                video=youtube_id(link)
            with LOCK:
                now=time.time()
                for k,j in list(JOBS.items()):
                    if j['status']=='waiting' and now-j['created']>300 or j['status'] in ('done','error') and now-j['created']>3600:JOBS.pop(k,None)
                if any(j['status'] in ('waiting','uploading','running') for j in JOBS.values()):h._send({'error':'Another job is active. Finish it first, or restart the local app.'},409);return True
                while len(JOBS)>=8:JOBS.pop(next(iter(JOBS)))
                id=uuid.uuid4().hex;j={'status':'running' if video else 'waiting','stage':'Waiting for file','progress':0,'created':now,'opts':opts};JOBS[id]=j
            if video:
                j.pop('opts');threading.Thread(target=execute,args=(j,video,opts,True),daemon=True).start()
            h._send({'id':id});return True
        if method=='POST' and path=='/studio-api/upload':
            q=urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query);id=(q.get('id') or [''])[0]
            n=int(h.headers.get('Content-Length','0'))
            if not 0<n<=MAX_UPLOAD:raise ValueError('Choose a file up to 512 MB.')
            with LOCK:
                j=JOBS.get(id)
                if not j or j['status']!='waiting':raise ValueError('Upload session expired.')
                j.update(status='uploading',stage='Receiving local file');opts=j.pop('opts')
            fd,name=tempfile.mkstemp(suffix='.media');
            try:
                with os.fdopen(fd,'wb') as f:
                    remain=n
                    while remain:
                        data=h.rfile.read(min(remain,1024*1024))
                        if not data:raise ValueError('Incomplete upload.')
                        f.write(data);remain-=len(data)
                j.update(status='running');threading.Thread(target=execute,args=(j,name,opts),daemon=True).start()
            except Exception:
                os.unlink(name);opts.clear();j.update(status='error',error='Upload failed.');raise
            h._send({'id':id});return True
        if method=='POST' and path=='/studio-api/clear-cache':
            with LOCK:
                if any(j['status'] in ('waiting','uploading','running') for j in JOBS.values()):raise ValueError('Wait for the current job to finish.')
                shutil.rmtree(CACHE,ignore_errors=True)
            h._send({'ok':True});return True
        h._send({'error':'Unknown endpoint'},404)
    except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e:h._send({'error':str(e)[:300]},400)
    except Exception:h._send({'error':'Local service error'},500)
    return True
