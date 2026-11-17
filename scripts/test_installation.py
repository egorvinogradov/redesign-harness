import plistlib
import tempfile
import unittest
from pathlib import Path

from director import check_service_workspace, service_identity


class InstallationTests(unittest.TestCase):
    def test_service_instances_do_not_replace_default(self):
        default, default_path = service_identity()
        other, other_path = service_identity('project-two')
        self.assertNotEqual(default, other)
        self.assertNotEqual(default_path, other_path)
        for invalid in ['../other', '', 'UPPER', 'a/b', 'x' * 49]:
            with self.assertRaises(ValueError):
                service_identity(invalid)

    def test_existing_service_only_updates_its_own_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plist = root / 'service.plist'
            home = root / 'workspace'
            check_service_workspace(plist, home)
            plist.write_bytes(plistlib.dumps({'ProgramArguments': ['python3', 'server.py', '--home', str(home)]}))
            check_service_workspace(plist, home)
            with self.assertRaises(ValueError):
                check_service_workspace(plist, root / 'different')
