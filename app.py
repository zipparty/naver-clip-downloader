import os, tempfile, shutil, subprocess, json, re
from urllib.parse import urlparse, parse_qs, urljoin, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
from urllib.error import HTTPError
from flask import Flask, request, jsonify, send_file, render_template_string
app=Flask(__name__)
HTML='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>NAVER CLIP DOWNLOADER</title><style>*{box-sizing:border-box}body{font:16px system-ui;background:#f5f6f7;color:#202124;margin:0}main{max-width:640px;margin:8vh auto;padding:24px}h1{font-size:25px}form{display:flex;gap:8px}input{min-width:0;flex:1;padding:14px;border:1px solid #ccc;border-radius:10px}button{border:0;background:#03a94f;color:white;padding:14px 22px;border-radius:10px;cursor:pointer}video,img{display:block;max-width:100%;max-height:65vh;margin:20px auto;border-radius:12px}dialog{border:0;border-radius:16px;padding:24px;box-shadow:0 10px 60px #0004}dialog::backdrop{background:#0007}#cancel{background:#777}small{color:#666}</style><main><h1 style="margin-bottom:6px">NAVER CLIP DOWNLOADER</h1><p style="font-size:12px;color:#666;margin:0 0 16px">주소 형식: https://naver.me/_________</p><form id="f"><input id="u" type="url" required placeholder="네이버 클립 주소 입력"><button>확인</button></form><p id="status" role="status"></p><section id="preview"></section><button id="again" hidden>다운로드</button></main><dialog id="d"><p>다운로드 받으시겠습니까?</p><button id="yes">예</button> <button id="cancel">아니오</button></dialog><script>const $=id=>document.getElementById(id);let current='';$('f').onsubmit=async e=>{e.preventDefault();$('again').hidden=true;$('preview').replaceChildren();$('status').textContent='영상 확인 중…';const url=$('u').value;try{const r=await fetch('/info?url='+encodeURIComponent(url));if(!(r.headers.get('content-type')||'').includes('application/json'))throw Error('서버 응답 오류 ('+r.status+'). 다시 시도해 주세요.');const j=await r.json();if(!r.ok)throw Error(j.error);current=url;const t=document.createElement('h3');t.textContent=j.title;$('preview').append(t);if(j.preview){const v=document.createElement('video');v.controls=true;v.playsInline=true;v.poster=j.thumbnail||'';v.src=j.preview;$('preview').append(v);v.onerror=()=>{$('status').textContent='미리보기 재생 불가. 원본 페이지에서 확인할 수 있습니다.'}}else if(j.thumbnail){const i=document.createElement('img');i.src=j.thumbnail;$('preview').append(i)}$('status').textContent=j.preview?'':'썸네일 미리보기';$('again').hidden=false;$('d').showModal()}catch(e){$('status').textContent=e.message}};$('again').onclick=()=>$('d').showModal();$('cancel').onclick=()=>$('d').close();$('yes').onclick=()=>{$('d').close();$('status').textContent='다운로드 요청 중…';location.href='/download?url='+encodeURIComponent(current)};</script>'''
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
    p=urlparse(u)
    q=parse_qs(p.query)
    mid=q.get('seedMediaId',q.get('mediaId',['']))[0]
    service=q.get('serviceType',['CLIP'])[0]
    if not re.fullmatch(r'[A-Fa-f0-9]{32,64}',mid) or not re.fullmatch(r'[A-Z0-9_]{1,20}',service):
        raise ValueError('클립 영상 ID를 확인할 수 없습니다.')
    params={'seedMediaId':mid,'seedType':'SPECIFIC','serviceType':service,'mediaType':'VOD','panelType':'share','referer':u,'recType':q.get('recType',['AIRS'])[0],'enableReverse':'false','adAllowed':'Y','clickNsc':'share','deviceType':'html5_mo'}
    headers={'User-Agent':'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36','Referer':'https://m.naver.com/','Origin':'https://m.naver.com','Accept':'application/json'}
    for version in ('v9','v5'):
        try:
            api='https://api-videohub.naver.com/shortformhub/feeds/'+version+'/card?'+urlencode(params)
            with build_opener(NoRedirect()).open(Request(api,headers=headers),timeout=12) as r: data=json.load(r)
            content=data['card']['content']; vod=content['vod']
            if vod.get('playable') is False: raise ValueError('재생할 수 없는 영상입니다.')
            if content.get('mediaId') and content['mediaId'].upper()!=mid.upper(): raise ValueError('다른 영상이 반환되었습니다.')
            candidates=[]
            for mpd in vod['playback']['MPD']:
                for period in mpd.get('Period',[]):
                    for aset in period.get('AdaptationSet',[]):
                        if aset.get('@mimeType')!='video/mp4' or aset.get('ContentProtection'): continue
                        for rep in aset.get('Representation',[]):
                            if rep.get('ContentProtection'): continue
                            for base in rep.get('BaseURL',[]):
                                if not isinstance(base,str): continue
                                parsed=urlparse(base)
                                if parsed.scheme=='https' and parsed.hostname and parsed.hostname.endswith('.pstatic.net') and not parsed.username and not parsed.password:
                                    candidates.append((int(rep.get('@bandwidth',0)),base))
            if candidates: return dict(title=content.get('title') or '네이버 클립',thumbnail=None,preview=max(candidates)[1])
        except Exception as e: app.logger.warning('Clip API %s failed: %s',version,type(e).__name__)
    raise ValueError('클립 재생 정보를 가져오지 못했습니다.')
@app.get('/')
def index():return render_template_string(HTML)
@app.get('/info')
def info():
    try:
        u=validated()
        if urlparse(u).hostname=='m.naver.com' and urlparse(u).path.startswith('/shorts'): return jsonify(clip_info(u))
        j=json.loads(run(['--dump-single-json','--skip-download','--',u]).stdout)
        formats=[f for f in j.get('formats',[]) if f.get('protocol')=='https' and f.get('ext')=='mp4' and f.get('vcodec') not in (None,'none') and f.get('acodec') not in (None,'none') and not f.get('has_drm')]
        return jsonify(title=j.get('title','네이버 클립'),thumbnail=j.get('thumbnail'),preview=formats[-1]['url'] if formats else None)
    except ValueError as e:return jsonify(error=str(e)),400
    except subprocess.CalledProcessError as e:
        app.logger.warning('Extractor failed: %s', (e.stderr or '')[-1000:])
        return jsonify(error='네이버 클립 영상 추출 실패 (현재 재생 형식 미지원)'),422
    except subprocess.TimeoutExpired:return jsonify(error='영상 조회 시간 초과'),504
    except Exception:
        app.logger.exception('Video lookup failed')
        return jsonify(error='영상 조회 실패'),422
@app.get('/download')
def download():
    folder=tempfile.mkdtemp()
    try:
        u=validated()
        if urlparse(u).hostname=='m.naver.com' and urlparse(u).path.startswith('/shorts'):
            media=clip_info(u)['preview']
            with build_opener(NoRedirect()).open(Request(media,headers={'User-Agent':'Mozilla/5.0','Referer':'https://m.naver.com/'}),timeout=25) as src, open(folder+'/clip.mp4','wb') as out:
                total=0
                while True:
                    chunk=src.read(1024*1024)
                    if not chunk: break
                    total+=len(chunk)
                    if total>200*1024*1024: raise ValueError('용량 제한 초과')
                    out.write(chunk)
        else: run(['-f','bv[ext=mp4]+ba[ext=m4a]/b[ext=mp4]','--merge-output-format','mp4','--max-filesize','200M','-o',folder+'/clip.%(ext)s','--',u],180)
        path=folder+'/clip.mp4'
        if not os.path.isfile(path):raise RuntimeError()
        response=send_file(path,as_attachment=True,download_name='naver_clip.mp4')
        response.call_on_close(lambda: shutil.rmtree(folder,ignore_errors=True))
        response.direct_passthrough=False
        return response
    except Exception:
        shutil.rmtree(folder,ignore_errors=True);return '다운로드 실패: 지원하지 않는 영상이거나 용량 제한을 초과했습니다.',422
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
