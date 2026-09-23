import base64
import copy
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
from server import Store, Conflict, Handler, ThreadingHTTPServer
from mcp_server import Bridge
from PIL import Image

class Codecs(unittest.TestCase):
    def test_all_catalog_profiles_export(self):
        for key,m in core.MODES.items():
            for chip in m['chips']:
                with self.subTest(mode=key,chip=chip):
                    w,h=(6,8) if m['encoding']=='text' else ((64,48) if key=='screen3' else (16,16))
                    a=core.asset(chip,key,w,h); data,files,manifest=core.export_asset(a)
                    self.assertTrue(manifest['validation']['valid'])
                    with zipfile.ZipFile(io.BytesIO(data)) as z:self.assertIsNone(z.testzip())
                    self.assertEqual(Image.open(io.BytesIO(files['preview.png'])).size,(w,h))

    def test_screen2_known_bytes(self):
        a=core.asset('TMS9918A','screen2',8,8);a['frames'][0]['pixels']=[15,0]*32
        f,_=core.encode(a);self.assertEqual(f['patterns.bin'],b'\xaa'*8);self.assertEqual(f['colors.bin'],b'\xf0'*8)

    def test_text_six_bit_and_register7(self):
        a=core.asset('TMS9918A','text40',6,8);a['frames'][0]['pixels']=[15,0,15,0,15,0]*8
        f,_=core.encode(a);self.assertEqual(f['patterns.bin'],b'\xa8'*8);self.assertEqual(json.loads(f['text-colors.json'])['register7'],240)

    def test_screen1_group_across_tile_row(self):
        a=core.asset('TMS9918A','screen1',32,16);p=a['frames'][0]['pixels'];p[0]=2;p[8*32]=3
        self.assertFalse(core.validate(a)['valid'])
        with self.assertRaises(ValueError):core.encode(a)
        core.constrain(a,0);self.assertTrue(core.validate(a)['valid'])

    def test_screen2_limit_per_eight_pixels(self):
        a=core.asset('TMS9918A','screen2',16,8);p=a['frames'][0]['pixels'];p[0]=2;p[8]=3
        self.assertTrue(core.validate(a)['valid']);p[1]=3
        self.assertEqual(core.validate(a)['violationCount'],1)

    def test_sprite_quadrant_order(self):
        a=core.asset('TMS9918A','sprite1');p=a['frames'][0]['pixels']
        for x,y in [(0,0),(1,8),(10,0),(11,8)]:p[y*16+x]=7
        f,_=core.encode(a);pattern=f['patterns.bin'];self.assertEqual(len(pattern),32)
        self.assertEqual([pattern[i] for i in (0,8,16,24)],[128,64,32,16]);self.assertEqual(f['colors.bin'],b'\x07')

    def test_sprite2_per_line_and_padding(self):
        a=core.asset('V9938','sprite2',8,8);p=a['frames'][0]['pixels'];p[0]=2;p[8]=3
        f,_=core.encode(a);self.assertEqual(f['colors.bin'],bytes([2,3]+[0]*14))
        p[1]=3;self.assertFalse(core.validate(a)['valid'])

    def test_multicolor_names_and_pixel_order(self):
        a=core.asset('TMS9918A','screen3');p=a['frames'][0]['pixels'];p[0]=2;p[1]=7;p[2*64]=3;p[2*64+1]=4
        f,_=core.encode(a);self.assertEqual(f['patterns.bin'][0],0x27);self.assertEqual(f['patterns.bin'][2],0x34)
        self.assertEqual([f['names.bin'][i] for i in (0,32,64,96,128)],[0,0,0,0,32])
        for y in range(48):
            for x in range(64):
                n=f['names.bin'][(y//2)*32+x//2];b=f['patterns.bin'][n*8+(y%8)]
                self.assertEqual((b>>(0 if x%2 else 4))&15,p[y*64+x])

    def test_packed_rows_padding(self):
        a=core.asset('V9938','screen5',3,2);a['frames'][0]['pixels']=[1,2,3,4,5,6]
        f,_=core.encode(a);self.assertEqual(f['pixels.bin'],bytes.fromhex('12 30 45 60'))
        a=core.asset('V9938','screen6',4,1);a['frames'][0]['pixels']=[0,1,2,3]
        self.assertEqual(core.encode(a)[0]['pixels.bin'],b'\x1b')

    def test_v9990_rgb_and_palette_order(self):
        a=core.asset('V9990','b1_rgb15',4,1);a['frames'][0]['pixels']=[0x03e0,0x7c00,0x001f,0x7fff]
        a['palette'][0]='#ff0000';a['palette'][1]='#00ff00';a['palette'][2]='#0000ff'
        f,_=core.encode(a);self.assertEqual(f['pixels.bin'],bytes.fromhex('e0 03 00 7c 1f 00 ff 7f'));self.assertEqual(f['palette.bin'][:9],bytes([31,0,0,0,31,0,0,0,31]))

    def test_v9990_hires_alternating_banks(self):
        a=core.asset('V9990','b4_idx4',4,1);a['frames'][0]['pixels']=[1,18,3,20];a['palette'][18]='#ff0000'
        f,_=core.encode(a);self.assertEqual(f['pixels.bin'],bytes.fromhex('12 34'));self.assertEqual(f['palette.bin'][34*3:35*3],bytes([31,0,0]))
        a['frames'][0]['pixels'][1]=2;self.assertFalse(core.validate(a)['valid']);core.constrain(a,0);self.assertTrue(core.validate(a)['valid'])

    def test_v9990_tile_order(self):
        a=core.asset('V9990','p1',16,8);a['frames'][0]['pixels']=[1]*8+[2]*8
        a['frames'][0]['pixels']*=8
        f,_=core.encode(a);self.assertEqual(f['patterns.bin'],b'\x11'*32+b'\x22'*32)

    def test_yjk_known_decode(self):
        # Y=10, J=2, K=-3 -> R12 G7 B12.
        vals=core.yjk_decode(bytes([85,87,82,80]));self.assertEqual(vals,[7*1024+12*32+12]*4)
        self.assertEqual(core.yjk_decode(bytes([80]*4)),[10*1024+10*32+12]*4)
        self.assertEqual(core.yjk_decode(bytes([85,87,82,80]),uv=True),[12*1024+12*32+7]*4)

    def test_yjk_encoder_representable_gray(self):
        a=core.asset('V9958','screen12',4,1);a['frames'][0]['pixels']=[10*1057]*4
        f,d=core.encode(a);self.assertEqual(d,a['frames'][0]['pixels']);self.assertEqual(f['pixels.bin'],bytes([73,72,73,72]))

    def test_yae_palette_route(self):
        pal=core.default_palette('V9958',core.MODES['screen10']);d=core.yjk_decode(bytes([0xf8]*4),yae=True,palette=pal);self.assertEqual(d,[32767]*4)
        a=core.asset('V9958','screen10',4,1);a['frames'][0]['pixels']=[core.rgb15(core.rgb(pal[i])) for i in [2,4,8,15]]
        f,d=core.encode(a);self.assertEqual(len(f['pixels.bin']),4);self.assertEqual(d,core.yjk_decode(f['pixels.bin'],yae=True,palette=a['palette']))

    def test_image_reference_roundtrip_and_opaque_black(self):
        im=Image.new('RGBA',(16,16),(0,0,0,255));b=io.BytesIO();im.save(b,'PNG');encoded=base64.b64encode(b.getvalue()).decode()
        a=core.asset('TMS9918A','sprite1');core.image_import(a,encoded,as_reference=True);self.assertEqual(a['reference']['width'],16);core.check_asset(a)
        self.assertEqual(a['frames'][0]['pixels'],[0]*256)
        core.image_import(a,encoded);self.assertEqual(a['frames'][0]['pixels'],[1]*256)

    def test_validation_rejects_invalid_data(self):
        for change in [{'width':7},{'palette':['#000000']},{'id':'../escape'},{'frames':[{'duration':1,'pixels':[]}]}]:
            a=core.asset();a.update(change)
            with self.assertRaises(ValueError):core.check_asset(a)
        with self.assertRaises(ValueError):core.asset('TMS9918A','screen8')

class StateTests(unittest.TestCase):
    def test_fresh_project_is_blank_9918(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Store(folder)
            self.assertEqual(len(s.project['assets']),1)
            a=s.project['assets'][0]
            self.assertEqual((a['chip'],a['mode']),('TMS9918A','screen2'))
            self.assertTrue(all(v==0 for f in a['frames'] for v in f['pixels']))
            self.assertEqual(Store(folder).project,s.project)

    def test_region_transform_preserves_other_tiles(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Store(folder);a=core.asset('TMS9918A','screen2',16,8)
            s.project={'version':1,'assets':[a]};a['frames'][0]['pixels'][0]=7;a['frames'][0]['pixels'][15]=3
            s.mutate(dict(baseRevision=0,assetId=a['id'],action='transform',operation='flip_x',x=0,y=0,width=8,height=8))
            p=s.find(a['id'])['frames'][0]['pixels'];self.assertEqual(p[7],7);self.assertEqual(p[0],0);self.assertEqual(p[15],3)
            s.mutate(dict(baseRevision=1,assetId=a['id'],action='paint_rect',x=8,y=4,width=4,height=4,color=2))
            p=s.find(a['id'])['frames'][0]['pixels'];self.assertEqual(sum(v==2 for v in p),16);self.assertEqual(p[15],3)

    def test_spritesheet_frame_order(self):
        a=core.asset('V9938','screen5',8,8);a['frames']=[dict(pixels=[i]*64,duration=100) for i in range(10)]
        im=Image.open(io.BytesIO(core.spritesheet(a)))
        self.assertEqual(im.size,(64,16));self.assertEqual(im.getpixel((8,8))[:3],core.rgb(a['palette'][9]))

    def test_atomic_conflict_undo_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Store(folder);a=s.project['assets'][0];before=copy.deepcopy(s.project)
            s.mutate(dict(action='pixels',baseRevision=0,assetId=a['id'],points=[dict(x=0,y=0,color=3)]))
            with self.assertRaises(Conflict):s.mutate(dict(action='undo',baseRevision=0))
            with self.assertRaises(ValueError):s.mutate(dict(action='pixels',baseRevision=1,assetId=a['id'],points=[dict(x=0,y=0,color=999)]))
            self.assertEqual(s.rev,1);self.assertEqual(s.find(a['id'])['frames'][0]['pixels'][0],3)
            s.mutate(dict(action='undo',baseRevision=1));self.assertEqual(s.project['assets'],before['assets'])
            s.mutate(dict(action='redo',baseRevision=2));self.assertEqual(Store(folder).rev,3);self.assertEqual(Store(folder).project,s.project)

    def test_http_mcp_protocol_end_to_end(self):
        with tempfile.TemporaryDirectory() as folder:
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=Store(folder);server.token='test-session';thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            bridge=Bridge('http://127.0.0.1:'+str(server.server_port))
            try:
                st=json.loads(bridge.call('studio_state',{})['content'][0]['text']);a=st['assets'][0]
                r=bridge.call('studio_edit',dict(baseRevision=st['revision'],action='pixels',assetId=a['id'],points=[dict(x=0,y=0,color=7)]));rev=json.loads(r['content'][0]['text'])['revision']
                self.assertTrue(json.loads(bridge.call('studio_validate',dict(assetId=a['id']))['content'][0]['text'])['valid'])
                png=bridge.call('studio_preview',dict(assetId=a['id']))['content'][0];self.assertEqual(base64.b64decode(png['data'])[:8],b'\x89PNG\r\n\x1a\n')
                exported=json.loads(bridge.call('studio_export',dict(baseRevision=rev,assetId=a['id']))['content'][0]['text']);self.assertTrue(Path(exported['path']).is_file())
                reqs=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'}, {'jsonrpc':'2.0','id':2,'method':'tools/list'}, {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'studio_state','arguments':{}}}]
                run=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'mcp_server.py'),'--url',bridge.url],input='\n'.join(json.dumps(r) for r in reqs)+'\n',capture_output=True,text=True,encoding='utf8',timeout=20)
                self.assertEqual(run.returncode,0);replies=[json.loads(x) for x in run.stdout.splitlines()];self.assertEqual(len(replies),3);self.assertEqual(len(replies[1]['result']['tools']),10);self.assertIn('revision',replies[2]['result']['content'][0]['text'])
                import urllib.request,urllib.error
                bad=urllib.request.Request(bridge.url+'/api/mutate',data=b'{}',headers={'Origin':'https://external.invalid','Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(bad)
                self.assertEqual(err.exception.code,403)
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
