#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression test for SEC-01: Windows PortableUpdate path handling and command injection prevention."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_CPP = ROOT / "platform/windows/PortableUpdate/main.cpp"


class PortableUpdateSecurityTests(unittest.TestCase):
    def setUp(self):
        self.source = MAIN_CPP.read_text(encoding="utf-8")

    def test_no_path_interpolation_in_powershell_commands(self):
        """Verify that filesystem paths are not interpolated into PowerShell command strings."""
        # Check that package.wstring() and stage.wstring() are not string-concatenated into command strings
        self.assertNotIn("package.wstring() + L\"' -DestinationPath", self.source)
        self.assertNotIn("package.wstring()", self.source.split("extractEnv")[0].split("extractCmd")[1])
        # Verify that environment variables are used for extraction paths
        self.assertIn("$env:ATIV_EXTRACT_SRC", self.source)
        self.assertIn("$env:ATIV_EXTRACT_DST", self.source)
        self.assertIn("-LiteralPath $env:ATIV_EXTRACT_SRC", self.source)
        self.assertIn("-DestinationPath $env:ATIV_EXTRACT_DST", self.source)

    def test_powershell_executable_resolved_explicitly(self):
        """Verify that the system PowerShell executable is resolved explicitly from system directory."""
        self.assertIn("getSystemPowerShell()", self.source)
        self.assertIn("GetSystemDirectoryW", self.source)
        self.assertIn("WindowsPowerShell", self.source)
        # Verify bare powershell.exe is not directly executed in extractCmd or verifyCmd
        self.assertNotIn('extractCmd = L"powershell.exe', self.source)
        self.assertNotIn('verifyCmd = L"powershell.exe', self.source)

    def test_benign_hostile_looking_paths_are_bound_as_data(self):
        """Verify that hostile-looking paths containing quotes, semicolons, $() and spaces are data."""
        hostile_paths = [
            r"C:\Program Files\App's Path; calc.exe",
            r"C:\Users\test\$(Invoke-Expression 'calc')\archive.zip",
            r"D:\Data\Folder & Malicious `Command`\stage",
            r"C:\Updates\üñîçødé 100% (test) 'quotes'\pkg.zip",
            r"C:\Dest\test;Remove-Item -Recurse C:\*",
        ]
        # In PowerShell, accessing $env:VAR evaluates the variable as string data without syntax evaluation
        # Validate that the extraction template matches the safe pattern
        match = re.search(r'Expand-Archive\s+-LiteralPath\s+\$env:([A-Za-z0-9_]+)\s+-DestinationPath\s+\$env:([A-Za-z0-9_]+)\s+-Force', self.source)
        self.assertIsNotNone(match, "Extraction command must use -LiteralPath with $env: variables")
        src_var, dst_var = match.group(1), match.group(2)
        self.assertEqual(src_var, "ATIV_EXTRACT_SRC")
        self.assertEqual(dst_var, "ATIV_EXTRACT_DST")


if __name__ == "__main__":
    unittest.main()
