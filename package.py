"""Package only app sources, documentation, examples and verification evidence."""
from pathlib import Path
import hashlib
import json
import zipfile
import core

ROOT=Path(__file__).resolve().parent

def main():
    examples=ROOT/'examples';examples.mkdir(exist_ok=True)
    sample=core.demo_project()
    (examples/'demo.msxpix.json').write_text(json.dumps(sample,ensure_ascii=False,indent=2),encoding='utf8')
    (examples/'blank-asset.zip').write_bytes(core.export_asset(sample['assets'][0])[0])
    names=['core.py','server.py','mcp_server.py','launcher.py','package.py','start.cmd','setup.cmd','requirements.txt','README.md','LICENSE','THIRD_PARTY_NOTICES.md','.gitignore']
    files=[ROOT/n for n in names]
    for folder in ('web','docs','tests','examples','licenses'):
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    dist=ROOT/'dist';dist.mkdir(exist_ok=True)
    target=dist/'MSX-Pixel-Studio-1.0.0.zip'
    manifest={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,'MSX-Pixel-Studio/'+str(p.relative_to(ROOT)))
        z.writestr('MSX-Pixel-Studio/SHA256SUMS.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert hashlib.sha256(z.read('MSX-Pixel-Studio/'+name)).hexdigest()==digest
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.sha256').write_text(digest+'  '+target.name+'\n',encoding='ascii')
    print(json.dumps(dict(path=str(target),files=len(files),bytes=target.stat().st_size,sha256=digest,profiles=len(core.MODES),chipModePairs=sum(len(m['chips']) for m in core.MODES.values())),indent=2))

if __name__=='__main__':main()
