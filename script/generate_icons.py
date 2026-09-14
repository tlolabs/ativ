#!/usr/bin/env python3
"""Convert authoritative artwork to native resources; never redraw it."""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/icons'

def generate():
    light = Image.open(SOURCE / 'ATIV-light.png').convert('RGBA')
    dark = Image.open(SOURCE / 'ATIV-dark.png').convert('RGBA')
    mac = ROOT / 'platform/macos/Resources'
    win = ROOT / 'platform/windows/ATIV/Assets'
    linux = ROOT / 'platform/linux/data/icons'
    for folder in (mac, win, linux):
        folder.mkdir(parents=True, exist_ok=True)
    light.save(mac / 'ATIV.icns', sizes=[(s, s) for s in (16,32,64,128,256,512,1024)])
    light.save(win / 'ATIV.ico', sizes=[(s,s) for s in (16,24,32,48,64,128,256)])
    for size in (16,24,32,48,64,128,256,512):
        light.resize((size,size), Image.Resampling.LANCZOS).save(linux / f'{size}.png')
    for name, size in [('Square44x44Logo',44),('Square150x150Logo',150),('StoreLogo',50)]:
        for scale in (100,125,150,200,400):
            n = size*scale//100
            light.resize((n,n),Image.Resampling.LANCZOS).save(win / f'{name}.scale-{scale}.png')
    catalog = mac / 'Assets.xcassets/AppIcon.appiconset'
    catalog.mkdir(parents=True,exist_ok=True)
    entries=[]
    for size in (16,32,128,256,512):
        for scale in (1,2):
            name=f'icon_{size}x{size}@{scale}x.png'
            light.resize((size*scale,size*scale),Image.Resampling.LANCZOS).save(catalog/name)
            entries.append(dict(idiom='mac',size=f'{size}x{size}',scale=f'{scale}x',filename=name))
    (catalog/'Contents.json').write_text(json.dumps(dict(images=entries,info=dict(version=1,author='ATIV')),indent=2)+'\n')
    for name,source in [('AppArtwork',light),('AppArtworkDark',dark)]:
        folder=mac/f'Assets.xcassets/{name}.imageset'; folder.mkdir(parents=True,exist_ok=True)
        source.save(folder/'artwork.png')
        (folder/'Contents.json').write_text(json.dumps(dict(images=[dict(idiom='universal',filename='artwork.png')],info=dict(version=1,author='ATIV')),indent=2)+'\n')
    (mac/'Assets.xcassets/Contents.json').write_text('{"info":{"version":1,"author":"ATIV"}}\n')

if __name__ == '__main__': generate()
