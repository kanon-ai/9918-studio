"""MSX Pixel Studio: shared, deterministic asset model and hardware codecs."""
from __future__ import annotations
import base64
import copy
import io
import json
import math
import re
import struct
import uuid
import zipfile
from collections import Counter
from PIL import Image

VERSION = 1
CHIPS = ['TMS9918A', 'V9938', 'V9958', 'V9968', 'V9990']
MSX1 = ['#000000','#000000','#3eb849','#74d07d','#5955e0','#8076f1','#b95e51','#65dbef','#db6559','#ff897d','#ccc35e','#ded087','#3aa241','#b766b5','#cccccc','#ffffff']
MSX2 = ['#000000','#000000','#24db24','#6dff6d','#2424ff','#496dff','#b62424','#49dbff','#ff2424','#ff6d6d','#dbdb24','#dbdb92','#249224','#db49b6','#b6b6b6','#ffffff']
MODES = {}

def mode(id, label, chips, encoding, colors, width, height, note, kind='graphic'):
    MODES[id] = dict(id=id, label=label, chips=chips, encoding=encoding, colors=colors,
                     width=width, height=height, note=note, kind=kind)

classic = CHIPS[:4]
mode('text40','SCREEN 0 / TEXT 40',classic,'text',16,6,8,'6×8 / 全字形で前景・背景色を共有', 'character')
mode('text80','SCREEN 0 / TEXT 80',CHIPS[1:4],'text',16,6,8,'6×8 / 通常文字パターン。点滅属性は別管理', 'character')
mode('screen1','SCREEN 1 / GRAPHIC 1',classic,'g1',16,128,128,'8×8 / 連続する8文字で2色を共有', 'character')
mode('screen2','SCREEN 2 / GRAPHIC 2',classic,'g2',16,128,128,'8×8 / 横8ドットごとに2色', 'character')
mode('screen3','SCREEN 3 / MULTICOLOR',classic,'mc',16,64,48,'64×48 論理画素 / 実表示は各画素4×4')
mode('screen4','SCREEN 4 / GRAPHIC 3',CHIPS[1:4],'g2',16,128,128,'8×8 / 横8ドットごとに2色。スプライトはMode 2', 'character')
for n,w,c in [(5,256,16),(6,512,4),(7,512,16),(8,256,256)]:
    mode(f'screen{n}',f'SCREEN {n}',CHIPS[1:4], 'grb8' if n==8 else f'idx{int(math.log2(c))}',c,w,212,'左から上位bit / 行優先。SCREEN 8は固定GRB 3:3:2' if n==8 else 'パレット / 横方向パック / 192・212行の素材に対応')
for n in (10,11,12):
    mode(f'screen{n}',f'SCREEN {n} / '+('YJK' if n==12 else 'YJK + YAE'),CHIPS[2:4], 'yjk' if n==12 else 'yjae',32768,256,212,'4画素でJ/Kを共有。出力時に近似・再構成プレビューを生成')
mode('screen8ep','SCREEN 8 / EPAL 256',['V9968'],'idx8',256,256,212,'V9968拡張 / RGB555から256色。レジスタ初期化は利用側で指定')
mode('sprite1','SPRITE MODE 1',classic,'sp1',16,16,16,'8×8 / 16×16。透明＋1色 / 1ライン4枚', 'sprite')
mode('sprite2','SPRITE MODE 2',CHIPS[1:4],'sp2',16,16,16,'8×8 / 16×16。各行で透明＋1色 / 1ライン8枚。CC合成は別スプライト', 'sprite')
mode('sprite3','SPRITE MODE 3',['V9968'],'idx4',16,16,32,'V9968 / 4bpp原画。色0は透明 / サイズは8の倍数。属性テーブルは利用側', 'sprite')
mode('v9sprite','V9990 SPRITE',['V9990'],'idx4',16,16,16,'16×16 / 4bpp原画 / 透明＋15色。配置属性は利用側', 'sprite')
for p,w in [('p1',256),('p2',512)]:
    mode(p,f'V9990 {p.upper()}',['V9990'],'tile4',16,128,128,f'8×8 / 4bpp タイル原画。表示幅{w} / パレット1バンク。ネームテーブルは別管理', 'character')
# Resolution presets; actual display timing and interlace are the target program's responsibility.
for b,w,h in [('b0',192,240),('b1',256,212),('b2',384,240),('b3',512,212),('b4',768,240),('b5',640,400),('b6',640,480),('b7',1024,212)]:
    for enc,c,label in [('idx2',4,'BP2'),('idx4',16,'BP4'),('idx6',64,'BP6'),('grb8',256,'BD8'),('rgb15',32768,'BD16'),('yjk',32768,'BYJK'),('yuv',32768,'BYUV'),('yjae',32768,'BYJKP'),('yuae',32768,'BYUVP')]:
        if b in ('b4','b5','b6','b7') and enc not in ('idx2','idx4'): continue
        mode(f'{b}_{enc}',f'V9990 {b.upper()} / {label}',['V9990'],enc,c,w,h,'素材の色データ。BP6は1画素1byte / 高解像度モードはBP2・BP4。転送先pitchは利用側で指定')
        if b in ('b4','b5','b6','b7'):
            MODES[f'{b}_{enc}']['colors']=c*2
            MODES[f'{b}_{enc}']['note']=f'偶数Xは色0〜{c-1}、奇数Xは色{c}〜{c*2-1}。奇数側はハードウェアのパレット32番から配置。'

def highres(a): return a['mode'].split('_')[0] in ('b4','b5','b6','b7')

def rgb(s):
    return tuple(int(s[i:i+2],16) for i in (1,3,5))

def hexcolor(t):
    return '#'+''.join(f'{max(0,min(255,round(v))):02x}' for v in t)

def grb_palette(chip):
    # V9938's blue levels map to 0,2,4,7 on the 3-bit DAC.
    if chip=='V9990':
        rg=[0,4,9,13,18,22,27,31]; blue=[0,11,21,31]
        return [hexcolor((rg[(i>>2)&7]*255/31,rg[i>>5]*255/31,blue[i&3]*255/31)) for i in range(256)]
    return [hexcolor((((i>>2)&7)*255/7,(i>>5)*255/7,[0,2,4,7][i&3]*255/7)) for i in range(256)]

def default_palette(chip, m):
    if m['encoding']=='grb8': return grb_palette(chip)
    base = MSX1 if chip=='TMS9918A' else MSX2
    count = min(m['colors'],256)
    if m['encoding'] in ('rgb15','yjk','yjae','yuv','yuae'): count=16
    colors = (base + [hexcolor(((i//36)*51,((i//6)%6)*51,(i%6)*51)) for i in range(216)] + ['#808080']*40)[:count]
    bits = 5 if chip in ('V9968','V9990') else 3
    return [hexcolor(tuple(round(v*((1<<bits)-1)/255)*255/((1<<bits)-1) for v in rgb(c))) for c in colors] if chip!='TMS9918A' else colors

def integer(v, low, high, name):
    if type(v) is not int or not low<=v<=high: raise ValueError(f'{name}: {low}..{high} の整数が必要です')
    return v

def asset(chip='TMS9918A', mode_id='screen2', width=None, height=None, name='Untitled'):
    if mode_id not in MODES or chip not in MODES[mode_id]['chips']: raise ValueError('VDPとモードの組み合わせが不正です')
    m=MODES[mode_id]; w=m['width'] if width is None else width; h=m['height'] if height is None else height
    integer(w,1,1024,'width'); integer(h,1,512,'height')
    a=dict(id=uuid.uuid4().hex[:12],name=str(name)[:100],chip=chip,mode=mode_id,width=w,height=h,palette=default_palette(chip,m),frames=[dict(pixels=[0]*(w*h),duration=150)],reference=None,notes='')
    if highres(a): a['frames'][0]['pixels']=[(x%2)*(m['colors']//2) for y in range(h) for x in range(w)]
    check_asset(a)
    return a

def direct(a): return MODES[a['mode']]['encoding'] in ('rgb15','yjk','yjae','yuv','yuae')

def check_asset(a):
    if not isinstance(a,dict): raise ValueError('asset must be object')
    m=MODES.get(a.get('mode')); chip=a.get('chip')
    if not m or chip not in m['chips']: raise ValueError('Unknown VDP/mode')
    w=integer(a.get('width'),1,1024,'width'); h=integer(a.get('height'),1,512,'height')
    e=m['encoding']
    if e=='text' and (w%6 or h%8): raise ValueError('TEXT素材は幅6・高さ8の倍数です')
    if e in ('g1','g2','tile4') and (w%8 or h%8): raise ValueError('タイル素材は8の倍数です')
    if e=='g1' and w*h//64>256: raise ValueError('SCREEN 1は最大256文字です')
    if e=='g2' and w*h//64>768: raise ValueError('SCREEN 2/4は最大768文字です')
    if e=='text' and w*h//48>256: raise ValueError('TEXTは最大256文字です')
    if e in ('sp1','sp2') and (w!=h or w not in (8,16)): raise ValueError('Sprite 1/2は8×8または16×16です')
    if a['mode']=='v9sprite' and (w,h)!=(16,16): raise ValueError('V9990スプライト原画は16×16です')
    if a['mode']=='sprite3' and (w%8 or h%8 or w>256 or h>256): raise ValueError('Sprite 3は8の倍数、最大256×256です')
    if e in ('yjk','yjae','yuv','yuae') and w%4: raise ValueError('YJK/YUVの幅は4の倍数です')
    if e=='mc' and (w!=64 or h!=48): raise ValueError('SCREEN 3は64×48論理画素です')
    if not isinstance(a.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',a['id']): raise ValueError('Invalid asset id')
    if not isinstance(a.get('name'),str) or len(a['name'])>100: raise ValueError('Invalid name')
    palette=a.get('palette',[])
    if len(palette)!=len(default_palette(chip,m)): raise ValueError('Palette size mismatch')
    for c in palette:
        if not isinstance(c,str) or len(c)!=7 or not c.startswith('#'): raise ValueError('Palette must be #rrggbb')
        rgb(c)
        if chip!='TMS9918A' and e!='grb8':
            steps=31 if chip in ('V9968','V9990') else 7
            if c.lower()!=hexcolor(tuple(round(v*steps/255)*255/steps for v in rgb(c))): raise ValueError('Palette values must align to RGB333/RGB555 hardware levels')
    if e=='grb8' and palette!=grb_palette(chip): raise ValueError('GRB固定パレットは編集できません')
    if chip=='TMS9918A' and palette!=MSX1: raise ValueError('TMS9918A固定パレットは編集できません')
    frames=a.get('frames')
    if not isinstance(frames,list) or not 1<=len(frames)<=64 or w*h*len(frames)>4_194_304: raise ValueError('Frame capacity exceeded')
    for f in frames:
        integer(f.get('duration'),20,10000,'duration')
        if not isinstance(f.get('pixels'),list) or len(f['pixels'])!=w*h: raise ValueError('Pixel count mismatch')
        for p in f['pixels']: integer(p,0,32767 if direct(a) else len(palette)-1,'pixel')
    ref=a.get('reference')
    if ref is not None:
        if not isinstance(ref,dict) or not isinstance(ref.get('data'),str) or len(ref['data'])>12_000_000: raise ValueError('Invalid reference')
        if not ref['data'].startswith('data:image/png;base64,'): raise ValueError('Reference must be PNG')
        for k in ('x','y','width','height','opacity'):
            if type(ref.get(k)) not in (int,float) or not math.isfinite(ref[k]): raise ValueError('Invalid reference transform')
        if not 0<=ref['opacity']<=1 or not 0<ref['width']<=4096 or not 0<ref['height']<=4096: raise ValueError('Invalid reference size/opacity')
    if not isinstance(a.get('notes',''),str) or len(a.get('notes',''))>10000: raise ValueError('Invalid notes')

def check_project(p):
    if not isinstance(p,dict) or p.get('version')!=VERSION: raise ValueError('Unsupported project version')
    if 'revision' in p: integer(p['revision'],0,9_007_199_254_740_991,'revision')
    if not isinstance(p.get('assets'),list) or not 1<=len(p['assets'])<=128: raise ValueError('Asset count must be 1..128')
    ids=set(); total=0
    for a in p['assets']:
        check_asset(a)
        if a['id'] in ids: raise ValueError('Duplicate asset ID')
        ids.add(a['id']); total+=a['width']*a['height']*len(a['frames'])
    if total>8_388_608: raise ValueError('Project pixel capacity exceeded')

def color_rgb(a,p):
    if direct(a): return (((p>>5)&31)*255//31,((p>>10)&31)*255//31,(p&31)*255//31)
    return rgb(a['palette'][p])

def rgb15(c):
    r,g,b=(round(v*31/255) for v in c)
    return (g<<10)|(r<<5)|b

def preview(a, frame=0, pixels=None, scale=1):
    integer(frame,0,len(a['frames'])-1,'frame'); integer(scale,1,16,'scale')
    if a['width']*a['height']*scale*scale>16_777_216: raise ValueError('Preview exceeds 16M pixels; reduce scale')
    im=Image.new('RGBA',(a['width'],a['height']))
    sprite=MODES[a['mode']]['kind']=='sprite'
    im.putdata([(*color_rgb(a,p),0 if sprite and p==0 else 255) for p in (pixels if pixels is not None else a['frames'][frame]['pixels'])])
    if scale!=1: im=im.resize((im.width*scale,im.height*scale),Image.Resampling.NEAREST)
    out=io.BytesIO(); im.save(out,'PNG'); return out.getvalue()

def spritesheet(a):
    cols=min(8,len(a['frames'])); rows=math.ceil(len(a['frames'])/cols)
    im=Image.new('RGBA',(a['width']*cols,a['height']*rows))
    for i in range(len(a['frames'])):
        with Image.open(io.BytesIO(preview(a,i))) as tile: im.paste(tile,((i%cols)*a['width'],(i//cols)*a['height']))
    out=io.BytesIO();im.save(out,'PNG');return out.getvalue()

def groups(a):
    w,h=a['width'],a['height']; e=MODES[a['mode']]['encoding']
    if e=='text': return [(list(range(w*h)),2)]
    if e=='sp1': return [(list(range(w*h)),1)]
    if e=='sp2': return [(list(range(y*w,(y+1)*w)),1) for y in range(h)]
    if e=='g2': return [(list(range(y*w+x,y*w+x+8)),2) for y in range(h) for x in range(0,w,8)]
    if e=='g1':
        tiles=[[ (ty+y)*w+tx+x for y in range(8) for x in range(8)] for ty in range(0,h,8) for tx in range(0,w,8)]
        return [(sum(tiles[i:i+8],[]),2) for i in range(0,len(tiles),8)]
    return []

def validate(a, frame=None):
    check_asset(a); errors=[]; count=0; issp=MODES[a['mode']]['encoding'] in ('sp1','sp2')
    for fi in (range(len(a['frames'])) if frame is None else [integer(frame,0,len(a['frames'])-1,'frame')]):
        p=a['frames'][fi]['pixels']
        if highres(a):
            half=MODES[a['mode']]['colors']//2
            for i,v in enumerate(p):
                if v//half!=(i%a['width'])%2:
                    count+=1
                    if len(errors)<128: errors.append(dict(frame=fi,x=i%a['width'],y=i//a['width'],colors=[v],limit=half,message='偶数・奇数Xのパレットバンク違反'))
        for indices,limit in groups(a):
            colors=sorted({p[i] for i in indices} - ({0} if issp else set()))
            if len(colors)>limit:
                count+=1
                if len(errors)<128: errors.append(dict(frame=fi,x=indices[0]%a['width'],y=indices[0]//a['width'],colors=colors,limit=limit,message=f'{len(colors)}色 / 上限{limit}色'))
    e=MODES[a['mode']]['encoding']; warnings=[]
    if e in ('yjk','yjae','yuv','yuae'): warnings.append('共有クロマへの近似変換あり。encoded-preview.pngで出力結果を確認してください。')
    if a['chip']=='V9968': warnings.append('V9968原画データ。FPGA/エミュレーターごとの拡張レジスタ設定・属性配置は対象プログラム側で行ってください。')
    return dict(valid=count==0,violationCount=count,violations=errors,warnings=warnings,assetId=a['id'],mode=a['mode'],hardwareTested=False)

def nearest(c, palette): return min(range(len(palette)), key=lambda i:sum((c[k]-palette[i][k])**2 for k in range(3)))

def constrain(a, frame):
    p=a['frames'][frame]['pixels']; pal=[rgb(c) for c in a['palette']]; sprite=MODES[a['mode']]['encoding'] in ('sp1','sp2')
    if highres(a):
        half=MODES[a['mode']]['colors']//2
        for i,v in enumerate(p):
            start=(i%a['width']%2)*half
            if not start<=v<start+half:p[i]=start+nearest(pal[v],pal[start:start+half])
    for indices,limit in groups(a):
        freq=Counter(p[i] for i in indices if not sprite or p[i]!=0)
        keep=[c for c,n in freq.most_common(limit)]
        if not keep: continue
        for i in indices:
            if sprite and p[i]==0: continue
            if p[i] not in keep: p[i]=keep[nearest(pal[p[i]],[pal[k] for k in keep])]

def image_import(a, encoded, frame=0, as_reference=False, fit='contain', dither=False):
    if len(encoded)>16_000_000: raise ValueError('Image is too large (12MB max)')
    data=base64.b64decode(encoded.split(',')[-1],validate=True)
    with Image.open(io.BytesIO(data)) as src:
        if src.width*src.height>16_000_000: raise ValueError('Image exceeds 16M pixels')
        if src.format not in ('PNG','JPEG','BMP','GIF','WEBP'): raise ValueError('Unsupported image type')
        im=src.convert('RGBA')
    if as_reference:
        im.thumbnail((2048,2048)); b=io.BytesIO(); im.save(b,'PNG'); ratio=min(a['width']/im.width,a['height']/im.height)
        a['reference']=dict(data='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode(),x=0,y=0,width=im.width*ratio,height=im.height*ratio,opacity=.4)
        return
    integer(frame,0,len(a['frames'])-1,'frame')
    w,h=a['width'],a['height']
    if fit not in ('contain','stretch'): raise ValueError('fit must be contain or stretch')
    if fit=='contain':
        im.thumbnail((w,h),Image.Resampling.LANCZOS); canvas=Image.new('RGBA',(w,h)); canvas.paste(im,((w-im.width)//2,(h-im.height)//2)); im=canvas
    else: im=im.resize((w,h),Image.Resampling.LANCZOS)
    pal=[rgb(c) for c in a['palette']]; cache={}; result=[]
    rgba=im.tobytes()
    for i in range(w*h):
        c=rgba[i*4:i*4+4]
        if c[3]<128:
            result.append((i%w%2)*(MODES[a['mode']]['colors']//2) if highres(a) else 0); continue
        cc=c[:3]
        if dither:
            delta=([-8,0,-6,2,4,-4,6,-2,-5,3,-7,1,7,-1,5,-3][(i//w%4)*4+i%w%4])*3
            cc=tuple(max(0,min(255,v+delta)) for v in cc)
        if direct(a): result.append(rgb15(cc))
        else:
            start=(i%w%2)*(MODES[a['mode']]['colors']//2) if highres(a) else (1 if MODES[a['mode']]['kind']=='sprite' else 0)
            end=start+MODES[a['mode']]['colors']//2 if highres(a) else len(pal)
            key=(cc,start)
            if key not in cache: cache[key]=start+nearest(cc,pal[start:end])
            result.append(cache[key])
    a['frames'][frame]['pixels']=result; constrain(a,frame)

def packed(values,bits):
    if bits in (6,8): return bytes(values)
    out=bytearray(); per=8//bits
    for i in range(0,len(values),per):
        b=0
        for j in range(per): b|=(values[i+j] if i+j<len(values) else 0) << (8-bits*(j+1))
        out.append(b)
    return bytes(out)

def yjk_decode(data, uv=False, yae=False, palette=None):
    out=[]
    for i in range(0,len(data),4):
        q=data[i:i+4]; k=(q[0]&7)|((q[1]&7)<<3); j=(q[2]&7)|((q[3]&7)<<3)
        if k>=32:k-=64
        if j>=32:j-=64
        for b in q:
            if yae and b&8:
                out.append(rgb15(rgb(palette[b>>4]))); continue
            y=b>>3; r=y+j; g=y+k; blue=(5*y-2*j-k)//4
            if uv: r,g,blue=r,blue,g
            out.append((max(0,min(31,g))<<10)|(max(0,min(31,r))<<5)|max(0,min(31,blue)))
    return out

def encode_yjk(a,p):
    e=MODES[a['mode']]['encoding']; uv=e in ('yuv','yuae'); yae=e in ('yjae','yuae'); data=bytearray(); decoded=[]
    pal=[rgb(c) for c in a['palette'][:16]]
    cache={}
    for pos in range(0,len(p),4):
        key=tuple(p[pos:pos+4])
        if key in cache:
            b,d=cache[key]; data.extend(b); decoded.extend(d); continue
        colors=[[((v>>5)&31),(v>>10)&31,v&31] for v in key]
        if uv: colors=[[r,b,g] for r,g,b in colors]
        ys=[(2*r+g+4*b)/8 for r,g,b in colors]
        jc=round(sum(c[0]-y for c,y in zip(colors,ys))/4); kc=round(sum(c[1]-y for c,y in zip(colors,ys))/4)
        best=None
        for j in range(max(-32,jc-2),min(31,jc+2)+1):
            for k in range(max(-32,kc-2),min(31,kc+2)+1):
                vals=[]; error=0
                for idx,c in enumerate(colors):
                    yc=round((c[0]-j+c[1]-k+(4*c[2]+2*j+k)/5)/3)
                    candidates=range(max(0,yc-3),min(31,yc+3)+1)
                    options=[]
                    for y in candidates:
                        if yae and y&1: continue
                        cr=[max(0,min(31,y+j)),max(0,min(31,y+k)),max(0,min(31,(5*y-2*j-k)//4))]
                        options.append((sum((v-t)**2 for v,t in zip(c,cr)),y<<3))
                    if yae:
                        target=color_rgb(a,key[idx]); pi=nearest(target,pal)
                        options.append((sum(((target[z]-pal[pi][z])*31/255)**2 for z in range(3)),(pi<<4)|8))
                    er,v=min(options); error+=er; vals.append(v)
                if best is None or error<best[0]: best=(error,vals,j,k)
        _,vals,j,k=best; lows=[k&7,(k>>3)&7,j&7,(j>>3)&7]; b=bytes(v|lo for v,lo in zip(vals,lows)); d=yjk_decode(b,uv,yae,a['palette'])
        data.extend(b); decoded.extend(d); cache[key]=(b,d)
    return bytes(data),decoded

def encode(a,frame=0):
    report=validate(a,frame)
    if not report['valid']: raise ValueError('色制約違反があります。検証結果を確認し、修正または「制約に合わせる」を実行してください。')
    p=a['frames'][frame]['pixels']; w,h=a['width'],a['height']; e=MODES[a['mode']]['encoding']; files={}; decoded=p
    if e in ('g1','g2','text'):
        tw=6 if e=='text' else 8; tiles=[[p[(ty+y)*w+tx+x] for y in range(8) for x in range(tw)] for ty in range(0,h,8) for tx in range(0,w,tw)]
        patterns=bytearray(); colors=bytearray(); common=sorted(set(p)); common=(common+[common[0]])[:2]
        for ti,t in enumerate(tiles):
            if e=='text': pair=common
            elif e=='g1':
                values=set(v for tile in tiles[ti//8*8:ti//8*8+8] for v in tile); pair=(sorted(values)+[min(values)])[:2]
                if ti%8==0: colors.append((pair[1]<<4)|pair[0])
            for y in range(8):
                row=t[y*tw:(y+1)*tw]
                if e=='g2': pair=(sorted(set(row))+[min(row)])[:2]; colors.append((pair[1]<<4)|pair[0])
                patterns.append(sum((1<<(7-x)) for x,v in enumerate(row) if v==pair[1] and pair[0]!=pair[1]))
        files['patterns.bin']=bytes(patterns)
        if colors: files['colors.bin']=bytes(colors)
        if e=='text': files['text-colors.json']=json.dumps(dict(foreground=common[1],background=common[0],register7=(common[1]<<4)|common[0])).encode()
    elif e in ('sp1','sp2'):
        # 16x16 order is left 16 rows followed by right 16 rows.
        files['patterns.bin']=bytes(sum((1<<(7-x)) for x in range(8) if p[y*w+tx+x]) for tx in range(0,w,8) for y in range(h))
        if e=='sp1': files['colors.bin']=bytes([next((v for v in p if v),0)])
        else: files['colors.bin']=bytes([next((v for v in p[y*w:(y+1)*w] if v),0) for y in range(h)]+([0]*8 if h==8 else []))
    elif e=='mc':
        # Canonical 32x24 name table: 4 character rows share one group of patterns.
        patterns=bytearray(1536); names=bytearray()
        for cy in range(24):
            for cx in range(32):
                n=(cy//4)*32+cx; names.append(n)
                for dy in range(2): patterns[n*8+(cy%4)*2+dy]=(p[(cy*2+dy)*w+cx*2]<<4)|p[(cy*2+dy)*w+cx*2+1]
        files={'patterns.bin':bytes(patterns),'names.bin':bytes(names)}
    elif e=='tile4':
        vals=[p[(ty+y)*w+tx+x] for ty in range(0,h,8) for tx in range(0,w,8) for y in range(8) for x in range(8)]
        files['patterns.bin']=packed(vals,4)
    elif e in ('yjk','yjae','yuv','yuae'):
        files['pixels.bin'],decoded=encode_yjk(a,p)
    elif e=='rgb15': files['pixels.bin']=struct.pack('<'+'H'*len(p),*p)
    else:
        bits=8 if e=='grb8' else int(e[3:]); values=[v&((1<<bits)-1) for v in p] if highres(a) else p
        files['pixels.bin']=b''.join(packed(values[y*w:(y+1)*w],bits) for y in range(h))
    if a['chip']!='TMS9918A' and e!='grb8':
        pal=bytearray()
        palette=a['palette']
        if highres(a):
            half=MODES[a['mode']]['colors']//2; palette=['#000000']*64
            palette[:half]=a['palette'][:half]; palette[32:32+half]=a['palette'][half:]
        for c in palette:
            r,g,b=rgb(c)
            if a['chip'] in ('V9968','V9990'):
                rr,gg,bb=[round(v*31/255) for v in (r,g,b)]
                pal.extend((rr,gg,bb))
            else: pal.extend(((round(r*7/255)<<4)|round(b*7/255),round(g*7/255)))
        files['palette.bin']=bytes(pal)
    return files,decoded

def export_asset(a,frame=0):
    files,decoded=encode(a,frame); report=validate(a,frame)
    errors=[sum((x-y)**2 for x,y in zip(color_rgb(a,v),color_rgb(a,d)))/3 for v,d in zip(a['frames'][frame]['pixels'],decoded)]
    report['encodedRMSE']=round(math.sqrt(sum(errors)/len(errors)),3)
    manifest=dict(version=VERSION,assetId=a['id'],name=a['name'],chip=a['chip'],mode=a['mode'],width=a['width'],height=a['height'],frame=frame,encoding=MODES[a['mode']]['encoding'],files={k:len(v) for k,v in files.items()},note='Raw asset components, not a VRAM image or BLOAD file. Tile order: row-major tiles; bitmap pitch: ceil(width*bpp/8), BP6=width. V9990 tile sheets must be placed at target VRAM stride. No register/attribute tables are generated.',validation=report)
    binary={k:v for k,v in files.items() if k.endswith('.bin')}
    asm=['; MSX Pixel Studio | '+a['chip']+' / '+a['mode']]; c=['#include <stdint.h>']
    for name,data in binary.items():
        ident=name.replace('.','_').replace('-','_'); asm.append(ident+':'); c.append(f'const uint8_t {ident}[{len(data)}] = {{')
        for i in range(0,len(data),16):
            asm.append('    db '+','.join(f'${v:02X}' for v in data[i:i+16])); c.append('    '+','.join(f'0x{v:02X}' for v in data[i:i+16])+',')
        c.append('};')
    files.update({'asset.asm':'\n'.join(asm).encode(),'asset.h':'\n'.join(c).encode(),'manifest.json':json.dumps(manifest,ensure_ascii=False,indent=2).encode(),'asset.json':json.dumps(a,ensure_ascii=False).encode(),'preview.png':preview(a,frame),'encoded-preview.png':preview(a,frame,decoded),'ai-report.json':json.dumps(report,ensure_ascii=False,indent=2).encode()})
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,d in files.items(): z.writestr(n,d)
    return out.getvalue(),files,manifest

def demo_project():
    """Start with an empty MSX1 pattern sheet; sample art is never editing data."""
    a=asset('TMS9918A','screen2',128,128,'部品セット')
    return dict(version=VERSION,name='9918 Studio',assets=[a])
