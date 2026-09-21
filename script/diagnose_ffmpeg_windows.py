#!/usr/bin/env python3
"""Record direct FFmpeg portrait-filter diagnostics independently of the Core API."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

runtime = Path(os.environ['ATIV_FFMPEG_RUNTIME'])
results = []
with tempfile.TemporaryDirectory(prefix='ativ-ffmpeg-diagnostic-') as directory:
    root = Path(directory)
    image = root / 'artwork.ppm'
    image.write_bytes(b'P6\n64 48\n255\n' + bytes(c for y in range(48) for x in range(64) for c in (x*4, y*5, (x*3+y*2)%256)))
    graph = '[0:v]split=2[bgsrc][fgsrc];[bgsrc]scale=90:160:force_original_aspect_ratio=increase,crop=90:160,gblur=sigma=40[bg];[fgsrc]scale=90:90:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[video]'
    for options in [[], ['-filter_complex_threads','1'], ['-filter_complex_threads','2'], ['-cpuflags','0'], ['-threads','1','-filter_complex_threads','1'], ['-cpuflags','0','-filter_complex_threads','1']]:
        command = [str(runtime/'ffmpeg.exe'), '-nostdin','-hide_banner','-loglevel','error','-y',*options,'-i',str(image),'-filter_complex',graph,'-map','[video]','-frames:v','1','-f','image2',str(root/'preview.png')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        record = {'options':options, 'returncode':result.returncode, 'stderr':result.stderr}
        print(json.dumps(record), flush=True)
        results.append(record)
Path('build/ffmpeg-windows-diagnostic.json').write_text(json.dumps(results,indent=2)+'\n')
