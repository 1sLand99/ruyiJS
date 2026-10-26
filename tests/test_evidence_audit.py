"""An unchanged report must not conceal corrupted evidence or a changed build."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.trace_audit.evidence_audit import audit_manifest
from tools.trace_audit.evidence_hashes import FileAudit, is_error, resolve_reference
from tools.trace_audit.evidence_refs import catalog, references


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.file = self.root / 'input.bin'
        self.file.write_bytes(b'original evidence')
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.audit = FileAudit()

    def check_file(self, expectation=None, role='evidence', name='input.bin'):
        return self.audit.check(self.root, name, expectation or self.sha, role, 'test')

    def test_matching_hash_and_size(self):
        row = self.check_file({'sha256': self.sha, 'bytes': 17})
        self.assertEqual(row['status'], 'match')
        self.assertFalse(is_error(row))

    def test_same_size_corruption_is_evidence_error(self):
        self.file.write_bytes(b'altered! evidence')
        row = self.check_file()
        self.assertEqual(row['status'], 'evidence_mismatch')
        self.assertTrue(is_error(row))

    def test_wrong_size_with_correct_hash_is_error(self):
        self.assertEqual(self.check_file({'sha256': self.sha, 'bytes': 1})['status'], 'evidence_mismatch')

    def test_working_document_source_and_build_drift_are_distinct(self):
        self.file.write_bytes(b'new version')
        for role in ('source', 'document', 'binary'):
            row = self.check_file(role=role)
            self.assertEqual(row['status'], {'binary': 'build_drift'}.get(role, role + '_drift'))
            self.assertFalse(is_error(row))
            self.assertEqual(row['expected_sha256'], self.sha)

    def test_no_digest_is_only_current_snapshot(self):
        self.assertEqual(self.check_file({'bytes': 17})['status'], 'snapshot_only')

    def test_missing_file_is_not_a_match(self):
        row = self.check_file(name='absent.bin')
        self.assertEqual(row['status'], 'missing')
        self.assertTrue(is_error(row))

    def test_malformed_digest_and_boolean_size_are_errors(self):
        for expected in ({'sha256': 'bad'}, {'sha256': self.sha, 'bytes': True}):
            self.assertEqual(self.check_file(expected)['status'], 'invalid_reference')

    def test_relative_path_has_one_declared_base(self):
        folder = self.root / 'nested'
        folder.mkdir()
        (folder / 'input.bin').write_bytes(b'other')
        self.assertEqual(resolve_reference(self.root, 'nested\\input.bin'), folder / 'input.bin')
        self.assertEqual(resolve_reference(folder, str(self.file)), self.file)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            resolve_reference(folder, '../input.bin')

    def test_absolute_metadata_path_overrides_label(self):
        data = {'reports': {'label': {'path': str(self.file), 'sha256': self.sha, 'bytes': 17}}}
        refs = list(references(data, self.root / 'manifest.json', self.root, self.root, self.root))
        self.assertEqual(self.audit.check(*refs[0])['status'], 'match')

    def test_tier_copy_uses_final_report_not_neighbor_with_same_name(self):
        entries = dict(catalog(self.root, self.root / 'project'))
        manifest = self.root / 'artifacts/tier-cost-20261024/validation.json'
        opts = entries[manifest]
        self.assertEqual(opts['outputs'], manifest.parent / 'final-report')
        data = {'outputs': {'TIER_COST.md': self.sha}}
        ref = next(references(data, manifest, self.root, self.root, self.root, **opts))
        self.assertEqual(ref[0], manifest.parent / 'final-report')

    def test_failed_build_not_treated_as_current_success(self):
        data = {'failed_shell_sha256': self.sha, 'restored_shell_sha256': self.sha,
                'verified_source_files': {'input.bin': True}}
        refs = list(references(data, self.root / 'restoration.json', self.root, self.root, self.root))
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0][-1], 'restored_shell_sha256')

    def test_markdown_in_legacy_sources_is_document_but_report_stays_evidence(self):
        data = {'sources': {'README.md': self.sha}, 'reports': {'PROOF.md': self.sha}}
        refs = list(references(data, self.root / 'manifest.json', self.root, self.root, self.root))
        self.assertEqual([row[-2] for row in refs], ['document', 'evidence'])

    def test_manifest_truth_flag_does_not_override_corrupted_file(self):
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'passed': True, 'reports': {'input.bin': self.sha}}), 'utf-8')
        self.file.write_bytes(b'changed')
        result = audit_manifest(self.audit, manifest, self.root, self.root, self.root)
        self.assertEqual(result['identity_errors'], 1)
        self.assertIn('passed', result['unhashed_top_level_fields'])


if __name__ == '__main__':
    unittest.main()
