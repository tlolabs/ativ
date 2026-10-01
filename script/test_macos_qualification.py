import stat
import subprocess
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest
import zipfile
from verify_macos_qualification import preflight_zip, compare_signed_build

class MacQualificationControls(unittest.TestCase):
    def test_traversal_and_link_writes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'package.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('../outside','bad')
            with self.assertRaises(ValueError):preflight_zip(path)
            with zipfile.ZipFile(path,'w') as z:
                link=zipfile.ZipInfo('App.app/link');link.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(link,'inside')
                z.writestr('App.app/link/file','bad')
            with self.assertRaises(ValueError):preflight_zip(path)
            with zipfile.ZipFile(path,'w') as z:
                link=zipfile.ZipInfo('App.app/link');link.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(link,'../../outside')
            with self.assertRaises(ValueError):preflight_zip(path)
    def test_framework_links_inside_root_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'package.zip'
            with zipfile.ZipFile(path,'w') as z:
                link=zipfile.ZipInfo('App.app/Contents/Frameworks/F.framework/Versions/Current')
                link.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(link,'B')
                z.writestr('App.app/Contents/Frameworks/F.framework/Versions/B/F','payload')
            preflight_zip(path)
    def test_changed_resources_cannot_be_blessed_as_signing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'original';new=root/'signed';old.mkdir();new.mkdir()
            (old/'resource').write_text('qualified');(new/'resource').write_text('changed')
            with self.assertRaisesRegex(ValueError,'resource'):compare_signed_build(old,new)

    def test_stapled_ticket_requires_apple_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'original';new=root/'signed';old.mkdir();(new/'Contents').mkdir(parents=True)
            (new/'Contents/CodeResources').write_bytes(b'fixture ticket')
            with patch('verify_macos_qualification.subprocess.run') as validate:
                compare_signed_build(old,new)
                self.assertEqual(validate.call_args.args[0],['xcrun','stapler','validate',str(new)])
                self.assertTrue(validate.call_args.kwargs['check'])
            with patch('verify_macos_qualification.subprocess.run',side_effect=subprocess.CalledProcessError(65,'stapler')):
                with self.assertRaises(subprocess.CalledProcessError):compare_signed_build(old,new)
    def test_valid_ticket_does_not_allow_added_resources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'original';new=root/'signed';old.mkdir();(new/'Contents/Resources').mkdir(parents=True)
            (new/'Contents/CodeResources').write_bytes(b'fixture ticket')
            (new/'Contents/Resources/CodeResources').write_bytes(b'unexpected resource')
            with patch('verify_macos_qualification.subprocess.run'):
                with self.assertRaisesRegex(ValueError,'payload files'):compare_signed_build(old,new)
    def test_ticket_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'original';new=root/'signed';old.mkdir();(new/'Contents').mkdir(parents=True)
            (new/'Contents/CodeResources').symlink_to('elsewhere')
            with self.assertRaisesRegex(ValueError,'regular file'):compare_signed_build(old,new)

if __name__=='__main__':unittest.main()
