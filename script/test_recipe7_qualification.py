#!/usr/bin/env python3
"""Candidate opt-in must not permit release or mutable/source-substituted input."""
import os
import unittest
from unittest.mock import patch
import qualify_recipe7 as q


class CandidateTrust(unittest.TestCase):
    def test_default_remains_production(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(q.enabled())

    def test_rejects_release_tags_stable_channel_and_invalid_opt_in(self):
        for changes in [{'ATIV_CHANNEL': 'stable'}, {'ATIV_RELEASE': '1'},
                        {'GITHUB_REF': 'refs/tags/v0.2.3'}, {'ATIV_QUALIFICATION_R7': 'true'}]:
            with patch.dict(os.environ, {'ATIV_QUALIFICATION_R7': '1', 'ATIV_CHANNEL': 'development', **changes}, clear=True):
                with self.assertRaises(ValueError):
                    q.enabled()

    def test_six_complete_immutable_pairs(self):
        self.assertEqual(len(q.LOCK['targets']), 6)
        for target in q.LOCK['targets'].values():
            self.assertEqual(len(target['binary_sha256']), 2)
            for value in [target['runtime_sha256'], target['source_sha256'], *target['binary_sha256'].values()]:
                self.assertRegex(value, r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
