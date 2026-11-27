import os, tempfile, shutil, subprocess, json, re, threading, time, uuid, base64, math
from urllib.parse import urlparse, parse_qs, urljoin, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
from urllib.error import HTTPError
from flask import Flask, request, jsonify, send_file, render_template_string
app=Flask(__name__)
app.logger.setLevel('INFO')
HTML='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>NAVER CLIP DOWNLOADER</title><style>*{box-sizing:border-box}body{font:16px system-ui;background:#f5f6f7;color:#202124;margin:0}main{max-width:640px;margin:8vh auto;padding:24px}h1{font-size:25px;margin-bottom:6px}form,.buttons{display:flex;gap:8px}input{min-width:0;flex:1;padding:14px;border:1px solid #ccc;border-radius:10px}button{border:0;background:#03a94f;color:white;padding:14px 22px;border-radius:10px;cursor:pointer}button:disabled{background:#c8ccca;cursor:default}video,img{display:block;max-width:100%;max-height:65vh;margin:20px auto;border-radius:12px}progress{width:100%;height:16px;accent-color:#03a94f}small{color:#666}.buttons button{flex:1}#g{margin:20px 0}</style><main><h1>NAVER CLIP DOWNLOADER</h1><p style="font-size:12px;color:#666;margin:0 0 16px">주소 형식: https://naver.me/_________</p><form id="f"><input id="u" type="url" required placeholder="네이버 클립 주소 입력"><button id="check">확인</button></form><p id="status" role="status"></p><section id="preview"></section><div class="buttons"><button id="extract" disabled>MP4 추출</button><button id="download" disabled>다운로드하기</button></div><div id="g" hidden><p id="pct">0%</p><progress id="bar" max="100" value="0"></progress></div></main><script>const $=id=>document.getElementById(id);let job='',timer=null;async function api(path,options){const r=await fetch(path,options);if(!(r.headers.get('content-type')||'').includes('application/json'))throw Error('서버 응답 오류 ('+r.status+')');const j=await r.json();if(!r.ok)throw Error(j.error);return j;}function reset(){clearTimeout(timer);job='';$('extract').disabled=true;$('download').disabled=true;$('preview').replaceChildren();$('g').hidden=true;$('bar').value=0;}function busy(v){$('check').disabled=v;$('u').disabled=v;}$('f').onsubmit=async e=>{e.preventDefault();reset();busy(true);$('status').textContent='영상 확인 중…';try{const j=await api('/info?url='+encodeURIComponent($('u').value));job=j.id;if(j.thumbnail){const img=document.createElement('img');img.src=j.thumbnail; $('preview').append(img);} $('status').textContent='추출 가능';$('extract').disabled=false;}catch(e){$('status').textContent=e.message}finally{busy(false)}};$('u').oninput=reset;$('extract').onclick=async()=>{busy(true);$('extract').disabled=true;$('download').disabled=true;$('g').hidden=false;$('pct').textContent='0%';$('status').textContent='영상 추출 중…';try{await api('/extract/'+job,{method:'POST'});poll();}catch(e){$('status').textContent=e.message;busy(false);$('extract').disabled=false;}};async function poll(){try{const j=await api('/status/'+job);if(j.percent===null){$('bar').removeAttribute('value');$('pct').textContent='추출 중 (전체 길이 확인 불가)';}else{$('bar').value=j.percent;$('pct').textContent=j.percent+'%';}if(j.state==='done'){$('status').textContent='추출 완료';$('download').disabled=false;busy(false);}else if(j.state==='error'){throw Error(j.error||'추출 실패');}else timer=setTimeout(poll,700);}catch(e){$('status').textContent=e.message;busy(false);$('extract').disabled=false;}}$('download').onclick=()=>location.href='/file/'+job;</script>'''
def validated():
    u=request.args.get('url',''); p=urlparse(u)
    if len(u)>2048 or p.scheme!='https' or p.username or p.password or p.hostname not in {'naver.me','clip.naver.com','m.clip.naver.com','m.blog.naver.com','blog.naver.com','tv.naver.com','m.tv.naver.com','m.naver.com','link.naver.com'}: raise ValueError('지원하는 네이버 HTTPS 주소를 입력하세요.')
    for _ in range(6):
        p=urlparse(u)
        if p.scheme!='https' or p.username or p.password or p.hostname not in {'naver.me','link.naver.com','m.naver.com','clip.naver.com','m.clip.naver.com','m.blog.naver.com','blog.naver.com','tv.naver.com','m.tv.naver.com'}: raise ValueError('지원하지 않는 연결 주소입니다.')
        if p.hostname=='link.naver.com':
            u=parse_qs(p.query).get('url',[''])[0]; continue
        if p.hostname!='naver.me': return u
        try:
            with build_opener(NoRedirect()).open(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=10) as r: return u
        except HTTPError as e:
            if e.code not in (301,302,303,307,308): raise
            u=urljoin(u,e.headers['Location'])
    raise ValueError('연결 주소가 너무 많습니다.')
def run(args, timeout=90):
    return subprocess.run(['yt-dlp','--ignore-config','--no-playlist','--no-warnings','--socket-timeout','15',*args],capture_output=True,text=True,check=True,timeout=timeout)
def clip_info(u):
    from playwright.sync_api import sync_playwright
    from urllib.parse import unquote
    candidates={}
    segments=set()
    seen=set()
    ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    def collect(url,ctype=''):
        p=urlparse(url)
        if not p.hostname: return
        seen.add((p.hostname,p.path[:120],ctype[:60]))
        if p.scheme!='https' or not p.hostname.endswith(('.pstatic.net','.naver.com')) or p.username or p.password: return
        path=unquote(p.path).lower()
        if path.endswith('.ts') or 'mp2t' in ctype:
            segments.add(url)
            return
        if '.m3u8' in path or 'mpegurl' in ctype: kind='hls'
        elif '.mpd' in path or 'dash+xml' in ctype: kind='dash'
        elif path.endswith('.mp4') and not re.search(r'(?:seg(?:ment)?|chunk|init)[-_]?\d',path): kind='mp4'
        elif 'video/mp4' in ctype and not path.endswith(('.m4s','.ts')): kind='mp4'
        else: return
        candidates[url]=kind
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required'])
        try:
            ctx=browser.new_context(viewport={'width':1280,'height':900},locale='ko-KR',timezone_id='Asia/Seoul',user_agent=ua)
            page=ctx.new_page()
            page.on('pageerror',lambda e:app.logger.info('Player JS error: %s',str(e)[:250]))
            page.on('requestfailed',lambda r:app.logger.info('Player request failed: %s %s',urlparse(r.url).hostname,r.failure))
            ctx.on('request',lambda req:collect(req.url))
            def response(res):
                try: collect(res.url,res.headers.get('content-type','').lower())
                except Exception: pass
            ctx.on('response',response)
            page.goto(u,wait_until='domcontentloaded',timeout=25000)
            duration=None
            for i in range(30):
                if i in (2,6,12):
                    for frame in page.frames:
                        try:
                            play=frame.get_by_role('button',name=re.compile(r'^(재생|영상 재생|동영상 재생|Play)$',re.I)).first
                            if play.is_visible(): play.click(timeout=1500); break
                            v=frame.locator('video').first
                            if v.is_visible(): v.click(timeout=1500); break
                        except Exception: pass
                for frame in page.frames:
                    try:
                        videos=frame.evaluate("""() => [...document.querySelectorAll('video')].map(v=>{v.muted=true;v.play().catch(()=>{});return {src:v.currentSrc||v.src,duration:Number.isFinite(v.duration)?v.duration:null}})""")
                        for v in videos:
                            if v.get('src'): collect(v['src'])
                            if v.get('duration'): duration=v['duration']
                    except Exception: pass
                if candidates and i>=3: break
                if segments and duration and i>=min(29,int(duration)+2): break
                page.wait_for_timeout(1000)
            app.logger.info('Player DOM: %s',page.evaluate("() => ({videos:[...document.querySelectorAll('video')].map(v=>({ready:v.readyState,error:v.error?.message,paused:v.paused})),buttons:[...document.querySelectorAll('button')].map(b=>b.getAttribute('aria-label')||b.innerText).filter(Boolean).slice(0,20),text:document.body.innerText.slice(0,500)})"))
            thumb=None
            if candidates or segments:
                try: thumb='data:image/jpeg;base64,'+base64.b64encode(page.screenshot(type='jpeg',quality=65,timeout=3000)).decode()
                except Exception: pass
            app.logger.info('Browser playback: host=%s title=%s requests=%s candidates=%s',urlparse(page.url).hostname,page.title()[:100],list(seen)[:80],len(candidates))
            app.logger.info('TS segments detected: %s',len(segments))
        finally: browser.close()
    if not candidates and segments:
        raise ValueError('TS 분할 영상은 발견했지만 전체 재생목록을 확인하지 못했습니다.')
    if not candidates: raise ValueError('브라우저에서 영상 스트림을 발견하지 못했습니다.')
    ordered=sorted(candidates,key=lambda x: {'hls':0,'dash':1,'mp4':2}[candidates[x]])
    return ordered,duration,thumb,ua
jobs={}
lock=threading.Lock()
MAX=200*1024*1024
def cleanup():
    for k,j in list(jobs.items()):
        if j['state']!='running' and time.time()-j['created']>1800:
            shutil.rmtree(j.get('folder',''),ignore_errors=True)
            jobs.pop(k,None)
def input_args(media,ua):
    return ['-rw_timeout','15000000','-protocol_whitelist','https,tls,tcp,crypto','-user_agent',ua,'-headers','Referer: https://m.naver.com/\r\n','-i',media]
def probe(media,ua):
    p=subprocess.run(['ffprobe','-v','error',*input_args(media,ua),'-show_entries','format=duration:stream=codec_type','-of','json'],capture_output=True,text=True,timeout=20,check=True)
    j=json.loads(p.stdout)
    if not any(s.get('codec_type')=='video' for s in j.get('streams',[])): raise ValueError('영상 트랙 없음')
    try:
        d=float(j.get('format',{}).get('duration',0))
        return d if math.isfinite(d) and d>0 else None
    except (ValueError,TypeError): return None
@app.get('/')
def index():return render_template_string(HTML)
@app.get('/info')
def info():
    try:
        with lock:
            cleanup()
            if len(jobs)>=12 or any(j['state']=='running' for j in jobs.values()): return jsonify(error='서버 사용 중입니다.'),429
        u=validated()
        media,duration,thumb,ua=clip_info(u)
        selected=None
        for candidate in media[:4]:
            try:
                d=probe(candidate,ua)
                selected=candidate
                duration=d or duration
                break
            except Exception: continue
        if not selected: raise ValueError('영상 스트림은 발견했지만 재생 가능한 파일을 확인하지 못했습니다.')
        key=uuid.uuid4().hex
        with lock:
            jobs[key]=dict(state='ready',percent=0,media=selected,duration=duration,ua=ua,created=time.time())
        return jsonify(id=key,thumbnail=thumb)
    except ValueError as e:return jsonify(error=str(e)),422
    except Exception:
        app.logger.exception('Browser lookup failed')
        return jsonify(error='영상 조회 실패'),422
def extract_worker(key):
    j=jobs[key]
    folder=tempfile.mkdtemp()
    j['folder']=folder
    path=folder+'/clip.mp4'
    proc=None
    try:
        cmd=['ffmpeg','-nostdin','-y','-v','error',*input_args(j['media'],j['ua']),'-map','0:v:0','-map','0:a:0?','-c','copy','-movflags','+faststart','-fs',str(MAX),'-progress','pipe:1','-nostats',path]
        with open(folder+'/error.log','w+') as err:
            proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=err,text=True)
            watchdog=threading.Timer(180,proc.kill)
            watchdog.start()
            try:
                for line in proc.stdout:
                    if line.startswith('out_time_us=') and j['duration']:
                        try:j['percent']=min(99,max(0,int(int(line.split('=',1)[1])/1000000/j['duration']*100)))
                        except ValueError:pass
                rc=proc.wait()
            finally:watchdog.cancel()
            if rc or not os.path.isfile(path) or os.path.getsize(path)>=MAX: raise RuntimeError('FFmpeg extraction failed')
        check=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type','-of','json',path],capture_output=True,text=True,timeout=15,check=True)
        result=json.loads(check.stdout)
        if not any(s.get('codec_type')=='video' for s in result.get('streams',[])): raise RuntimeError('No video')
        if j['duration'] and float(result.get('format',{}).get('duration',0))<j['duration']*0.95: raise RuntimeError('Incomplete file')
        j.update(state='done',percent=100,created=time.time())
    except Exception:
        app.logger.exception('Extraction failed')
        shutil.rmtree(folder,ignore_errors=True)
        j.update(state='error',error='MP4 추출 실패',created=time.time())
@app.post('/extract/<key>')
def extract(key):
    with lock:
        cleanup()
        j=jobs.get(key)
        if not j:return jsonify(error='영상 정보가 만료되었습니다.'),404
        if j['state']=='running':return jsonify(ok=True)
        if any(x['state']=='running' for x in jobs.values()):return jsonify(error='다른 영상 추출 중입니다.'),429
        j.update(state='running',percent=0 if j['duration'] else None)
        threading.Thread(target=extract_worker,args=(key,),daemon=True).start()
    return jsonify(ok=True)
@app.get('/status/<key>')
def status(key):
    j=jobs.get(key)
    if not j:return jsonify(error='영상 정보가 만료되었습니다.'),404
    return jsonify(state=j['state'],percent=j['percent'],error=j.get('error'))
@app.get('/file/<key>')
def file(key):
    j=jobs.get(key)
    if not j or j['state']!='done':return '파일이 준비되지 않았습니다.',404
    return send_file(j['folder']+'/clip.mp4',as_attachment=True,download_name='naver_clip.mp4')
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
