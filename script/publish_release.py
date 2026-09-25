#!/usr/bin/env python3
"""Publish valid packages even when another platform failed; never fabricate feeds."""
import hashlib,json,os,re,subprocess
from pathlib import Path
root=Path('release-assets')
assets=[p for p in root.iterdir() if p.is_file() and p.name.startswith('ATIV-')]
sboms=sorted(root.glob('ativ-*-sbom.cdx.json'))
if not assets: raise SystemExit('No passing package artifacts to publish')
base=re.search(r'^version = "([^"]+)"',Path('Cargo.toml').read_text(),re.M)[1]
stable=os.environ['ATIV_CHANNEL']=='stable'
version=base if stable else base+'-dev.'+os.environ['GITHUB_RUN_NUMBER']
tag='v'+base if stable else 'development'
if stable and os.environ['GITHUB_REF_NAME']!=tag: raise SystemExit('Tag/version mismatch')
if not all(p.name.startswith('ATIV-'+version+'-') for p in assets): raise SystemExit('Mixed artifact versions')
results=json.loads(os.environ['BUILD_RESULTS'])
failed=[name for name,result in results.items() if result['result']!='success']
notes=Path('build-release-notes.md')
status='<!-- ativ-build-status -->\n'+('Development build '+version if not stable else 'ATIV '+version)+'\n\n'+('Incomplete build: '+', '.join(failed)+'. Only validated passing artifacts are attached.\n' if failed else 'All target jobs passed.\n')+'\nSource: '+os.environ['GITHUB_SHA']+'\n<!-- /ativ-build-status -->\n'
notes.write_text(status)
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted([*assets,*sboms])))
def gh(*args,check=True):return subprocess.run(['gh',*map(str,args)],check=check)
exists=gh('release','view',tag,check=False).returncode==0
if not exists:
    gh('release','create',tag,'--target',os.environ['GITHUB_SHA'],'--title',('ATIV '+version),'--notes-file',notes,'--generate-notes',*(['--latest'] if stable else ['--prerelease','--latest=false']))
else:
    if stable:
        previous=json.loads(subprocess.check_output(['gh','release','view',tag,'--json','body']))['body']
        pattern=r'<!-- ativ-build-status -->.*?<!-- /ativ-build-status -->'
        notes.write_text(re.sub(pattern,lambda _:status.rstrip(),previous,flags=re.S) if re.search(pattern,previous,re.S) else status+'\n'+previous)
    else:
        gh('api','--method','PATCH','repos/'+os.environ['GITHUB_REPOSITORY']+'/git/refs/tags/development','-f','sha='+os.environ['GITHUB_SHA'],'-F','force=true')
    gh('release','edit',tag,'--title','ATIV '+version,'--notes-file',notes)
# Development artifact filenames include run number. Remove stale packages and feeds
# from the rolling prerelease so failed targets never advertise yesterday's build.
if not stable and exists:
    old=json.loads(subprocess.check_output(['gh','release','view',tag,'--json','assets']))['assets']
    for asset in old:gh('release','delete-asset',tag,asset['name'],'--yes')
gh('release','upload',tag,*assets,*sboms,root/'SHA256SUMS','--clobber')
with open(os.environ['GITHUB_ENV'],'a') as env:
    env.write('ATIV_VERSION='+version+'\nATIV_RELEASE_TAG='+tag+'\n')
