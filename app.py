import os, tempfile, shutil, subprocess, json
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file, render_template_string
app=Flask(__name__)
HTML='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>NAVER CLIP DOWNLOADER</title><style>*{box-sizing:border-box}body{font:16px system-ui;background:#f5f6f7;color:#202124;margin:0}main{max-width:640px;margin:8vh auto;padding:24px}h1{font-size:25px}form{display:flex;gap:8px}input{min-width:0;flex:1;padding:14px;border:1px solid #ccc;border-radius:10px}button{border:0;background:#03a94f;color:white;padding:14px 22px;border-radius:10px;cursor:pointer}video,img{display:block;max-width:100%;max-height:65vh;margin:20px auto;border-radius:12px}dialog{border:0;border-radius:16px;padding:24px;box-shadow:0 10px 60px #0004}dialog::backdrop{background:#0007}#cancel{background:#777}small{color:#666}</style><main><h1>NAVER CLIP DOWNLOADER</h1><form id="f"><input id="u" type="url" required placeholder="네이버 클립 주소 입력"><button>확인</button></form><p id="status" role="status"></p><section id="preview"></section><button id="again" hidden>다운로드</button></main><dialog id="d"><p>다운로드 받으시겠습니까?</p><button id="yes">예</button> <button id="cancel">아니오</button></dialog><script>const $=id=>document.getElementById(id);let current='';$('f').onsubmit=async e=>{e.preventDefault();$('again').hidden=true;$('preview').replaceChildren();$('status').textContent='영상 확인 중…';const url=$('u').value;try{const r=await fetch('/info?url='+encodeURIComponent(url));if(!(r.headers.get('content-type')||'').includes('application/json'))throw Error('서버 응답 오류 ('+r.status+'). 다시 시도해 주세요.');const j=await r.json();if(!r.ok)throw Error(j.error);current=url;const t=document.createElement('h3');t.textContent=j.title;$('preview').append(t);if(j.preview){const v=document.createElement('video');v.controls=true;v.playsInline=true;v.poster=j.thumbnail||'';v.src=j.preview;$('preview').append(v);v.onerror=()=>{$('status').textContent='미리보기 재생 불가. 원본 페이지에서 확인할 수 있습니다.'}}else if(j.thumbnail){const i=document.createElement('img');i.src=j.thumbnail;$('preview').append(i)}$('status').textContent=j.preview?'':'썸네일 미리보기';$('again').hidden=false;$('d').showModal()}catch(e){$('status').textContent=e.message}};$('again').onclick=()=>$('d').showModal();$('cancel').onclick=()=>$('d').close();$('yes').onclick=()=>{$('d').close();$('status').textContent='다운로드 요청 중…';location.href='/download?url='+encodeURIComponent(current)};</script>'''
def validated():
    u=request.args.get('url',''); p=urlparse(u)
    if len(u)>2048 or p.scheme!='https' or p.username or p.password or p.hostname not in {'naver.me','clip.naver.com','m.clip.naver.com','m.blog.naver.com','blog.naver.com','tv.naver.com','m.tv.naver.com'}: raise ValueError('지원하는 네이버 HTTPS 주소를 입력하세요.')
    return u
def run(args, timeout=90):
    return subprocess.run(['yt-dlp','--ignore-config','--no-playlist','--no-warnings','--socket-timeout','15',*args],capture_output=True,text=True,check=True,timeout=timeout)
@app.get('/')
def index():return render_template_string(HTML)
@app.get('/info')
def info():
    try:
        u=validated(); j=json.loads(run(['--dump-single-json','--skip-download','--',u]).stdout)
        formats=[f for f in j.get('formats',[]) if f.get('protocol')=='https' and f.get('ext')=='mp4' and f.get('vcodec') not in (None,'none') and f.get('acodec') not in (None,'none') and not f.get('has_drm')]
        return jsonify(title=j.get('title','네이버 클립'),thumbnail=j.get('thumbnail'),preview=formats[-1]['url'] if formats else None)
    except ValueError as e:return jsonify(error=str(e)),400
    except subprocess.CalledProcessError as e:
        app.logger.warning('Extractor failed: %s', (e.stderr or '')[-1000:])
        return jsonify(error='영상 추출 실패'),422
    except subprocess.TimeoutExpired:return jsonify(error='영상 조회 시간 초과'),504
    except Exception:
        app.logger.exception('Video lookup failed')
        return jsonify(error='영상 조회 실패'),422
@app.get('/download')
def download():
    folder=tempfile.mkdtemp()
    try:
        u=validated();run(['-f','bv[ext=mp4]+ba[ext=m4a]/b[ext=mp4]','--merge-output-format','mp4','--max-filesize','200M','-o',folder+'/clip.%(ext)s','--',u],180)
        path=folder+'/clip.mp4'
        if not os.path.isfile(path):raise RuntimeError()
        response=send_file(path,as_attachment=True,download_name='naver_clip.mp4')
        response.call_on_close(lambda: shutil.rmtree(folder,ignore_errors=True))
        response.direct_passthrough=False
        return response
    except Exception:
        shutil.rmtree(folder,ignore_errors=True);return '다운로드 실패: 지원하지 않는 영상이거나 용량 제한을 초과했습니다.',422
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
