"""Export complete evidence directories without changing their original bytes.

Example (paths are explicit; missing sources cause refusal):
  python scripts/export_release_evidence.py --out F:\\owtda\\delivery-new \
      --part repo=. --part sequence=F:\\owtda\\final-sequence \
      --part manifests=F:\\owtda\\manifests --part smoke=F:\\owtda\\smoke

This does not issue admission or rewrite any old seal/absolute reference. The
prefix map records how source paths map to portable parts. A nonempty destination
is always refused. Verify and archive an inactive, sealed source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):h.update(chunk)
    return h.hexdigest()


def export_parts(parts: dict[str, Path], out: Path) -> dict:
    if not parts:
        raise ValueError('at least one evidence part is required')
    out=out.resolve()
    for label, source in parts.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', label):
            raise ValueError('invalid part label')
        source=source.resolve()
        if not source.is_dir():raise FileNotFoundError(source)
        if out==source or out.is_relative_to(source):
            raise ValueError('output cannot be inside an exported source')
    out.mkdir(parents=True, exist_ok=False)
    objects=[]; prefixes={}
    for label, source in parts.items():
        source=source.resolve();prefixes[str(source)]=label
        for path in sorted(source.rglob('*')):
            if any(p in {'.git','__pycache__','.pytest_cache'} for p in path.relative_to(source).parts):continue
            if path.is_symlink():raise ValueError(f'symlink not exported: {path}')
            if not path.is_file():continue
            rel=Path(label)/path.relative_to(source);target=out/rel
            before=digest(path);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
            if digest(target)!=before or digest(path)!=before:
                raise RuntimeError(f'source changed during export: {path}')
            objects.append({'path':rel.as_posix(),'sha256':before,'bytes':target.stat().st_size})
    manifest={'schema_version':1,'kind':'PORTABLE_RELEASE_EVIDENCE','source_prefix_map':prefixes,
              'objects':objects,'admission_issued':False,
              'note':'Source bytes preserved. This package may contain failure evidence. No seal was reissued.'}
    (out/'PORTABLE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    (out/'SHA256SUMS.txt').write_text(''.join(o['sha256']+'  '+o['path']+'\n' for o in objects)+digest(out/'PORTABLE_MANIFEST.json')+'  PORTABLE_MANIFEST.json\n',encoding='utf-8')
    return manifest


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True);parser.add_argument('--part',action='append',required=True,metavar='LABEL=DIR')
    args=parser.parse_args();parts={}
    for part in args.part:
        label,sep,path=part.partition('=')
        if not sep or label in parts:raise SystemExit('invalid or duplicate --part')
        parts[label]=Path(path)
    result=export_parts(parts,Path(args.out));print(json.dumps({'files':len(result['objects']),'admission_issued':False}));return 0
if __name__=='__main__':raise SystemExit(main())
