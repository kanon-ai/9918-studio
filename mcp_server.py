"""MCP stdio JSON-RPC bridge; stdout is reserved for protocol messages."""
import argparse
import base64
import json
import sys
import urllib.request
import urllib.error

SCHEMAS={
 'studio_modes':('List VDP profiles, encodings and restrictions.',{}),
 'studio_state':('Get current revision and compact asset list. Read before mutating.',{}),
 'studio_asset':('Read full editable asset including pixels, frames and palette.',{'assetId':{'type':'string'}}),
 'studio_create':('Create an asset; dimensions must match mode alignment.',{'baseRevision':{'type':'integer'},'chip':{'type':'string'},'mode':{'type':'string'},'name':{'type':'string'},'width':{'type':'integer'},'height':{'type':'integer'}}),
 'studio_edit':('Apply atomic revision-checked operation. action: pixels(points [{x,y,color}]), frame_pixels(pixels), metadata(name/notes/palette/reference), paint_rect(x/y/width/height/color), transform(operation flip_x/flip_y/rotate/shift_left/shift_right/shift_up/shift_down/clear), constrain, add_frame(duplicate), delete_frame, duration(duration), duplicate, delete, undo, redo. Direct color pixels use GRB555 integers; others palette indices.',{'baseRevision':{'type':'integer'},'action':{'type':'string'},'assetId':{'type':'string'},'frame':{'type':'integer'},'points':{'type':'array','items':{'type':'object','properties':{'x':{'type':'integer'},'y':{'type':'integer'},'color':{'type':'integer'}},'required':['x','y','color']}},'pixels':{'type':'array','items':{'type':'integer'}},'operation':{'type':'string'},'name':{'type':'string'},'notes':{'type':'string'},'palette':{'type':'array','items':{'type':'string'}},'reference':{'type':['object','null']},'duplicate':{'type':'boolean'},'duration':{'type':'integer'},'x':{'type':'integer'},'y':{'type':'integer'},'width':{'type':'integer'},'height':{'type':'integer'},'color':{'type':'integer'}}),
 'studio_import_image':('Import base64 PNG/JPEG/BMP/GIF/WebP as tracing reference or quantized pixels. No external URLs.',{'baseRevision':{'type':'integer'},'assetId':{'type':'string'},'frame':{'type':'integer'},'image':{'type':'string'},'reference':{'type':'boolean'},'fit':{'type':'string','enum':['contain','stretch']},'dither':{'type':'boolean'}}),
 'studio_validate':('Check all frames for hardware color constraints. Does not change pixels.',{'assetId':{'type':'string'}}),
 'studio_preview':('Return a PNG image to the AI for visual inspection.',{'assetId':{'type':'string'},'frame':{'type':'integer'},'scale':{'type':'integer','minimum':1,'maximum':16}}),
 'studio_export':('Export ZIP into local data/exports; returns absolute path, SHA256, manifest and validation. Invalid color constraints block binary export.',{'baseRevision':{'type':'integer'},'assetId':{'type':'string'},'frame':{'type':'integer'}}),
 'studio_text':('Return ASM, C, asset JSON, manifest or AI report as text.',{'assetId':{'type':'string'},'frame':{'type':'integer'},'format':{'type':'string','enum':['asm','c','json','manifest','report']}})
}
REQUIRED={'studio_asset':['assetId'],'studio_create':['baseRevision','chip','mode','name'],'studio_edit':['baseRevision','action'],'studio_import_image':['baseRevision','assetId','image'],'studio_validate':['assetId'],'studio_preview':['assetId'],'studio_export':['baseRevision','assetId'],'studio_text':['assetId','format']}

class Bridge:
    def __init__(self,url):self.url=url.rstrip('/')
    def request(self,path,body=None,binary=False):
        headers={'X-Studio-Source':'MCP'}
        if body is not None:
            token=self.request('/api/session')['token']; headers.update({'X-Studio-Token':token,'Content-Type':'application/json'})
        req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=120) as r:data=r.read()
        except urllib.error.HTTPError as e:raise ValueError(e.read().decode()) from e
        except urllib.error.URLError as e:raise ValueError('MSX Pixel Studioを先に起動してください: '+self.url) from e
        return data if binary else json.loads(data)
    def call(self,name,a):
        from urllib.parse import urlencode
        if name not in SCHEMAS:raise ValueError('Unknown tool')
        for key in REQUIRED.get(name,[]):
            if key not in a:raise ValueError('Missing '+key)
        q=urlencode(dict(asset=a.get('assetId',''),frame=a.get('frame',0),scale=a.get('scale',1),format=a.get('format','zip')))
        if name=='studio_modes':r=self.request('/api/modes')
        elif name in ('studio_state','studio_asset'):
            s=self.request('/api/state')
            if name=='studio_asset':
                found=[x for x in s['project']['assets'] if x['id']==a['assetId']]
                if not found:raise ValueError('Asset not found')
                r=dict(revision=s['revision'],asset=found[0])
            else:r=dict(revision=s['revision'],assets=[{k:v for k,v in x.items() if k not in ('frames','reference')}|{'frameCount':len(x['frames'])} for x in s['project']['assets']],events=s['events'],undo=s['undo'],redo=s['redo'])
        elif name in ('studio_create','studio_edit','studio_import_image'):
            b=dict(a)
            if name=='studio_create':b['action']='create'
            elif name=='studio_import_image':b['action']='import_image'
            elif b['action'] not in ('pixels','frame_pixels','metadata','paint_rect','transform','constrain','add_frame','delete_frame','duration','duplicate','delete','undo','redo'):raise ValueError('Unsupported edit action')
            s=self.request('/api/mutate',b);r=dict(revision=s['revision'],assetId=s.get('assetId',a.get('assetId')),event=s['events'][-1])
        elif name=='studio_validate':r=self.request('/api/validate?'+q)
        elif name=='studio_preview':return {'content':[{'type':'image','mimeType':'image/png','data':base64.b64encode(self.request('/api/preview?'+q,binary=True)).decode()}]}
        elif name=='studio_export':r=self.request('/api/write-export',a)
        elif name=='studio_text':
            path='/api/report?' if a['format']=='report' else '/api/export?'
            return {'content':[{'type':'text','text':self.request(path+q,binary=True).decode()}]}
        return {'content':[{'type':'text','text':json.dumps(r,ensure_ascii=False)}]}
    def handle(self,req):
        method=req.get('method'); p=req.get('params',{})
        if method=='initialize':return {'protocolVersion':'2024-11-05','capabilities':{'tools':{},'resources':{}},'serverInfo':{'name':'msx-pixel-studio','version':'1.0.0'},'instructions':'Local MSX editor. Always read revision before writes. Validate and request preview before exporting.'}
        if method=='ping':return {}
        if method=='tools/list':return {'tools':[dict(name=n,description=d,inputSchema={'type':'object','properties':s,'required':REQUIRED.get(n,[]),'additionalProperties':False}) for n,(d,s) in SCHEMAS.items()]}
        if method=='tools/call':
            try:return self.call(p['name'],p.get('arguments',{}))
            except Exception as e:return {'isError':True,'content':[{'type':'text','text':str(e)}]}
        if method=='resources/list':return {'resources':[{'uri':'msxstudio://project','name':'Current project','mimeType':'application/json'}]}
        if method=='resources/read':
            if p.get('uri')!='msxstudio://project':raise ValueError('Unknown resource')
            return {'contents':[{'uri':p['uri'],'mimeType':'application/json','text':json.dumps(self.request('/api/state'),ensure_ascii=False)}]}
        raise LookupError('Method not found')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');args=parser.parse_args();bridge=Bridge(args.url)
    sys.stdin.reconfigure(encoding='utf8');sys.stdout.reconfigure(encoding='utf8')
    for line in sys.stdin:
        try:
            req=json.loads(line)
            if 'id' not in req:continue
            try:response={'jsonrpc':'2.0','id':req['id'],'result':bridge.handle(req)}
            except LookupError as e:response={'jsonrpc':'2.0','id':req['id'],'error':{'code':-32601,'message':str(e)}}
            except Exception as e:response={'jsonrpc':'2.0','id':req['id'],'error':{'code':-32602,'message':str(e)}}
        except Exception:response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}}
        print(json.dumps(response,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
