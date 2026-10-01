#!/usr/bin/env python3
"""Record and check every locked Avalonia/.NET package and its declared license."""
import argparse,json,os,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'platform/avalonia/packages.lock.json'
INVENTORY=ROOT/'docs/avalonia-dependencies.json'

def packages():
    result={}
    for target,entries in json.loads(LOCK.read_text())['dependencies'].items():
        for name,detail in entries.items():
            key=(name,detail['resolved'])
            if key not in result:result[key]={'name':name,'version':detail['resolved'],'contentHash':detail['contentHash'],'targets':[]}
            assert result[key]['contentHash']==detail['contentHash'],'Inconsistent package hash across targets'
            result[key]['targets'].append(target)
    return sorted(result.values(),key=lambda x:(x['name'].lower(),x['version']))

def metadata(item):
    folder=Path(os.environ.get('NUGET_PACKAGES',Path.home()/'.nuget/packages'))/item['name'].lower()/item['version'].lower()
    nuspec=list(folder.glob('*.nuspec'))
    if len(nuspec)!=1:raise ValueError(f'Missing NuGet license metadata for {item["name"]}/{item["version"]}')
    node=next((x for x in ET.parse(nuspec[0]).getroot().iter() if x.tag.rsplit('}',1)[-1]=='license'),None)
    if node is None or not node.text:raise ValueError(f'Missing declared license: {item["name"]}')
    if node.get('type')=='file':
        license_text=(folder/node.text).read_text(errors='replace')
        if item['name']=='Avalonia.Angle.Windows.Natives' and 'Redistribution and use in source and binary forms' in license_text:return 'BSD-3-Clause'
        raise ValueError(f'Unreviewed package license file: {item["name"]}')
    if node.text!='MIT':raise ValueError(f'Unreviewed package license: {item["name"]} {node.text}')
    return node.text

def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
    locked=packages()
    if a.write:
        for item in locked:item['license']=metadata(item)
        INVENTORY.write_text(json.dumps({'schema':1,'project':'ATIV Avalonia','lockfile':'platform/avalonia/packages.lock.json','packages':locked},indent=2)+'\n')
    if a.check:
        prior=json.loads(INVENTORY.read_text())
        assert prior['schema']==1 and len(prior['packages'])==len(locked),'NuGet inventory does not cover all locked packages'
        for expected,actual in zip(locked,prior['packages']):
            assert all(actual[k]==expected[k] for k in expected),'NuGet inventory differs from the lockfile'
            assert actual['license'] in ('MIT','BSD-3-Clause'),'Unreviewed NuGet license'
        print(f"Audited {len(locked)} locked NuGet packages and license declarations")
if __name__=='__main__':main()
