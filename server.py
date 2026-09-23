"""Loopback editor API. UI and MCP share one atomic, revision-checked store."""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import webbrowser
import core

ROOT=Path(__file__).resolve().parent
MAX_BODY=64*1024*1024

class Conflict(ValueError): pass

class Store:
    def __init__(self, folder):
        self.folder=Path(folder); self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'project.json'; self.lock=threading.RLock(); self.undo=[]; self.redo=[]; self.rev=0
        if self.path.exists(): self.project=json.loads(self.path.read_text(encoding='utf8')); core.check_project(self.project)
        else: self.project=core.demo_project(); self.save()
        self.rev=self.project.get('revision',0)
        self.events=[]

    def save(self):
        temp=self.path.with_suffix('.tmp'); temp.write_text(json.dumps(self.project,ensure_ascii=False),encoding='utf8'); os.replace(temp,self.path)

    def state(self): return dict(revision=self.rev,project=copy.deepcopy(self.project),undo=len(self.undo),redo=len(self.redo),events=self.events[-15:])

    def find(self,id):
        for a in self.project['assets']:
            if a['id']==id:return a
        raise ValueError('Asset not found')

    def mutate(self,body,source='UI'):
        with self.lock:
            if type(body.get('baseRevision')) is not int or body['baseRevision']!=self.rev: raise Conflict(f'更新番号が一致しません。最新データを再取得してください (current={self.rev})')
            before=copy.deepcopy(self.project); oldundo=self.undo[:]; oldredo=self.redo[:]
            action=body.get('action'); result={}
            try:
                if action in ('undo','redo'):
                    src,dst=(self.undo,self.redo) if action=='undo' else (self.redo,self.undo)
                    if not src: raise ValueError('履歴がありません')
                    dst.append(before); self.project=src.pop()
                else:
                    if action=='replace':
                        self.project=copy.deepcopy(body['project'])
                    elif action=='create':
                        a=core.asset(body.get('chip','TMS9918A'),body.get('mode','screen2'),body.get('width'),body.get('height'),body.get('name','Untitled'))
                        self.project['assets'].append(a); result['assetId']=a['id']
                    elif action=='delete':
                        a=self.find(body['assetId'])
                        if len(self.project['assets'])==1:raise ValueError('最後の素材は削除できません')
                        self.project['assets'].remove(a)
                    elif action=='duplicate':
                        a=copy.deepcopy(self.find(body['assetId'])); a['id']=secrets.token_hex(6); a['name']=(a['name']+' copy')[:100]; self.project['assets'].append(a); result['assetId']=a['id']
                    else:
                        a=self.find(body['assetId']); frame=core.integer(body.get('frame',0),0,len(a['frames'])-1,'frame'); p=a['frames'][frame]['pixels']; w,h=a['width'],a['height']
                        if action=='pixels':
                            for point in body['points']:
                                x=core.integer(point['x'],0,w-1,'x'); y=core.integer(point['y'],0,h-1,'y'); p[y*w+x]=point['color']
                        elif action=='frame_pixels':
                            a['frames'][frame]['pixels']=body['pixels']
                        elif action=='metadata':
                            for key in ('name','notes','palette','reference'):
                                if key in body:a[key]=body[key]
                        elif action=='constrain':core.constrain(a,frame)
                        elif action=='import_image':core.image_import(a,body['image'],frame,body.get('reference',False),body.get('fit','contain'),body.get('dither',False))
                        elif action=='add_frame':
                            blank=[(x%2)*(core.MODES[a['mode']]['colors']//2) if core.highres(a) else 0 for y in range(h) for x in range(w)]
                            a['frames'].insert(frame+1,copy.deepcopy(a['frames'][frame]) if body.get('duplicate',True) else dict(pixels=blank,duration=150))
                        elif action=='delete_frame':
                            if len(a['frames'])==1:raise ValueError('最後のフレームは削除できません')
                            a['frames'].pop(frame)
                        elif action=='duration':a['frames'][frame]['duration']=body['duration']
                        elif action=='paint_rect':
                            x0=core.integer(body.get('x'),0,w-1,'x'); y0=core.integer(body.get('y'),0,h-1,'y')
                            rw=core.integer(body.get('width'),1,w-x0,'width'); rh=core.integer(body.get('height'),1,h-y0,'height')
                            for yy in range(y0,y0+rh):
                                for xx in range(x0,x0+rw):p[yy*w+xx]=body['color']
                        elif action=='transform':
                            op=body['operation']
                            if op not in ('flip_x','flip_y','rotate','shift_left','shift_right','shift_up','shift_down','clear'):raise ValueError('Unknown transform')
                            x0=core.integer(body.get('x',0),0,w-1,'x');y0=core.integer(body.get('y',0),0,h-1,'y')
                            rw=core.integer(body.get('width',w),1,w-x0,'width');rh=core.integer(body.get('height',h),1,h-y0,'height')
                            if op=='rotate' and rw!=rh:raise ValueError('90度回転は正方形領域のみです')
                            new=p[:]
                            for y in range(rh):
                                for x in range(rw):
                                    sx,sy=x,y
                                    if op=='flip_x':sx=rw-1-x
                                    elif op=='flip_y':sy=rh-1-y
                                    elif op=='rotate':sx,sy=y,rw-1-x
                                    elif op=='shift_left':sx=(x+1)%rw
                                    elif op=='shift_right':sx=(x-1)%rw
                                    elif op=='shift_up':sy=(y+1)%rh
                                    elif op=='shift_down':sy=(y-1)%rh
                                    new[(y0+y)*w+x0+x]=(((x0+x)%2)*(core.MODES[a['mode']]['colors']//2) if core.highres(a) else 0) if op=='clear' else p[(y0+sy)*w+x0+sx]
                            a['frames'][frame]['pixels']=new
                        else:raise ValueError('Unknown action')
                    core.check_project(self.project)
                    self.undo.append(before); self.redo=[]
                    # Bound history by pixels, not just operation count.
                    while len(self.undo)>40 or (len(self.undo)>1 and sum(sum(a['width']*a['height']*len(a['frames']) for a in q['assets']) for q in self.undo)>8_388_608):self.undo.pop(0)
                core.check_project(self.project); self.project['revision']=self.rev+1; self.save()
            except Exception:
                self.project=before; self.undo=oldundo; self.redo=oldredo; raise
            self.rev+=1; self.events.append(dict(revision=self.rev,source=source,action=action,time=time.strftime('%H:%M:%S'))); self.events=self.events[-100:]
            return dict(**self.state(),**result)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,data,status=200,ctype='application/json; charset=utf-8',filename=None):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(data)

    def guard(self,write=False):
        expected=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') not in (expected,f'localhost:{self.server.server_port}'): raise PermissionError('Loopback host required')
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://'+expected,f'http://localhost:{self.server.server_port}'):raise PermissionError('Cross-origin request denied')
        if write and self.headers.get('X-Studio-Token')!=self.server.token:raise PermissionError('Session token required')

    def do_GET(self):
        try:
            self.guard(); u=urlparse(self.path); q=parse_qs(u.query); path=u.path
            with self.server.store.lock:
                if path=='/api/health':return self.respond(dict(application='msx-pixel-studio',version='1.0.3'))
                if path=='/api/session':return self.respond(dict(token=self.server.token,revision=self.server.store.rev))
                if path=='/api/modes':return self.respond(dict(chips=core.CHIPS,modes=list(core.MODES.values())))
                if path=='/api/state':
                    if q.get('since')==[str(self.server.store.rev)]:return self.respond(dict(unchanged=True,revision=self.server.store.rev))
                    return self.respond(self.server.store.state())
                if path=='/api/project':return self.respond(self.server.store.project,filename='project.msxpix.json')
                if path in ('/api/validate','/api/preview','/api/export','/api/report'):
                    a=self.server.store.find(q.get('asset',[''])[0]); fi=int(q.get('frame',['0'])[0]); core.integer(fi,0,len(a['frames'])-1,'frame')
                    if path=='/api/validate':return self.respond(core.validate(a))
                    if path=='/api/preview':return self.respond(core.preview(a,fi,scale=int(q.get('scale',['1'])[0])),ctype='image/png')
                    if path=='/api/report':
                        return self.respond(dict(assetId=a['id'],name=a['name'],chip=a['chip'],mode=a['mode'],width=a['width'],height=a['height'],frames=len(a['frames']),palette=a['palette'],notes=a.get('notes',''),validation=core.validate(a),revision=self.server.store.rev),filename='ai-report.json')
                    if q.get('format')==['png']:return self.respond(core.preview(a,fi),ctype='image/png',filename='preview.png')
                    if q.get('format')==['json']:return self.respond(a,filename='asset.json')
                    if q.get('format')==['sheet']:return self.respond(core.spritesheet(a),ctype='image/png',filename='spritesheet.png')
                    data,files,manifest=core.export_asset(a,fi); fmt=q.get('format',['zip'])[0]
                    if fmt=='zip':return self.respond(data,ctype='application/zip',filename='msx-asset.zip')
                    names={'asm':'asset.asm','c':'asset.h','json':'asset.json','manifest':'manifest.json','encoded':'encoded-preview.png'}
                    if fmt not in names:raise ValueError('Unknown export format')
                    name=names[fmt]; return self.respond(files[name],ctype='image/png' if fmt=='encoded' else 'text/plain; charset=utf-8',filename=name)
            if path=='/':path='/index.html'
            if path not in ('/index.html','/app.js','/style.css'):return self.respond(dict(error='Not found'),404)
            data=(ROOT/'web'/path[1:]).read_bytes(); return self.respond(data,ctype={'/index.html':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path])
        except PermissionError as e:self.respond(dict(error=str(e)),403)
        except (ValueError,KeyError,TypeError) as e:self.respond(dict(error=str(e)),400)
        except Exception as e:self.respond(dict(error=str(e)),500)

    def do_POST(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=MAX_BODY:raise ValueError('Request body exceeds limit')
            raw=self.rfile.read(n)
            self.guard(True)
            body=json.loads(raw)
            if not isinstance(body,dict):raise ValueError('Expected object')
            if self.path=='/api/mutate':return self.respond(self.server.store.mutate(body,'MCP' if self.headers.get('X-Studio-Source')=='MCP' else 'UI'))
            if self.path=='/api/write-export':
                with self.server.store.lock:
                    if body.get('baseRevision')!=self.server.store.rev:raise Conflict('Export revision mismatch')
                    a=self.server.store.find(body['assetId']); data,_,manifest=core.export_asset(a,body.get('frame',0))
                    name=f"{a['id']}-r{self.server.store.rev}-f{body.get('frame',0)}.zip"; dest=self.server.store.folder/'exports'/name; dest.parent.mkdir(exist_ok=True); dest.write_bytes(data)
                    return self.respond(dict(path=str(dest),sha256=hashlib.sha256(data).hexdigest(),manifest=manifest))
            self.respond(dict(error='Not found'),404)
        except Conflict as e:self.respond(dict(error=str(e),revision=self.server.store.rev),409)
        except PermissionError as e:self.respond(dict(error=str(e)),403)
        except (ValueError,KeyError,TypeError,IndexError) as e:self.respond(dict(error=str(e)),400)
        except Exception as e:self.respond(dict(error=str(e)),500)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--data',type=Path,default=ROOT/'data'); parser.add_argument('--no-browser',action='store_true'); args=parser.parse_args()
    store=Store(args.data); server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler); server.store=store; server.token=secrets.token_urlsafe(32)
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'MSX Pixel Studio: {url}\nProject: {store.path}',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
