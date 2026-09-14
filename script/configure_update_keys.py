#!/usr/bin/env python3
"""One-time bootstrap. Refuses to replace existing repository update trust keys."""
import argparse,base64,json,os,subprocess
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption

def main():
    p=argparse.ArgumentParser();p.add_argument('--backup',type=Path,required=True);a=p.parse_args()
    repo='tlolabs/ativ'
    for kind,key in [('secret','ATIV_UPDATE_PRIVATE_KEY'),('variable','ATIV_UPDATE_PUBLIC_KEY')]:
        values=json.loads(subprocess.check_output(['gh',kind,'list','--repo',repo,'--json','name']))
        if any(v['name']==key for v in values):raise SystemExit('Existing update trust configuration found; refusing rotation')
    a.backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    key=Ed25519PrivateKey.generate()
    seed=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
    public=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    fd=os.open(a.backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as backup:backup.write(seed+b'\n')
    # Private material goes through stdin, never command arguments, logs or source files.
    subprocess.run(['gh','secret','set','ATIV_UPDATE_PRIVATE_KEY','--repo',repo],input=seed,check=True,capture_output=True)
    subprocess.run(['gh','variable','set','ATIV_UPDATE_PUBLIC_KEY','--repo',repo,'--body',public],check=True,capture_output=True)
    print('Created ATIV update trust configuration. Private backup: '+str(a.backup))
if __name__=='__main__':main()
