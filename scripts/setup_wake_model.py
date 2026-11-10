"""Download pinned offline wake model assets to this D-drive project only."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    manifest=json.loads((ROOT/'config/wake_model.json').read_text(encoding='utf-8'))
    destination=(ROOT/manifest['directory']).resolve()
    model_root=(ROOT/'tmp/models').resolve()
    if not destination.is_relative_to(model_root):raise ValueError('Unsafe model destination')
    model_root.mkdir(parents=True,exist_ok=True)
    archive=model_root/'sherpa-kws-zh-en-3M-2025-12-20.tar.bz2'
    source=manifest['source']
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest()!=source['sha256']:
        total=0
        with httpx.Client(timeout=60,follow_redirects=True) as client,client.stream('GET',source['url']) as response:
            response.raise_for_status()
            with archive.open('wb') as output:
                for chunk in response.iter_bytes():
                    total+=len(chunk)
                    if total>source['bytes']:raise ValueError('Model download exceeded pinned size')
                    output.write(chunk)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=source['sha256']:
        raise ValueError('Wake archive digest mismatch')
    destination.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive,'r:bz2') as package:
        for name,digest in manifest['sha256'].items():
            target=(destination/name).resolve()
            if not target.is_relative_to(destination):raise ValueError('Unsafe model member')
            member=package.getmember(destination.name+'/'+name)
            if not member.isfile():raise ValueError('Expected a regular model file')
            with package.extractfile(member) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Wake model digest mismatch')
    print('Offline keyword model ready; no recordings or credentials were uploaded.')


if __name__=='__main__':main()
