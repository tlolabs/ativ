#!/usr/bin/env python3
import math,struct,sys,wave
from pathlib import Path
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
(root/'artwork ü.ppm').write_bytes(b'P6\n48 32\n255\n'+bytes(c for y in range(32) for x in range(48) for c in (x*5,y*7,100)))
with wave.open(str(root/'audio ü.wav'),'wb') as audio:
    audio.setparams((1,2,8000,0,'NONE','not compressed'))
    audio.writeframes(b''.join(struct.pack('<h',round(10000*math.sin(2*math.pi*440*i/8000))) for i in range(8000)))
