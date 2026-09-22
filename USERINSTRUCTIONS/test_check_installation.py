"""Tests for the read-only installation diagnostic, not a trading adapter."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installation_diagnostic', HERE / 'check_installation.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class FileChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sample.txt').write_bytes(b'known data')
        self.wanted = hashlib.sha256(b'known data').hexdigest()

    def status(self, name, wanted=None):
        return check.verify_files(self.root, {name: wanted or self.wanted})[0]['status']

    def test_valid_file(self):
        self.assertEqual(self.status('sample.txt'), 'OK')

    def test_missing_file(self):
        self.assertEqual(self.status('missing.txt'), 'MISSING')

    def test_changed_file(self):
        (self.root / 'sample.txt').write_text('changed')
        self.assertEqual(self.status('sample.txt'), 'HASH_MISMATCH')

    def test_directory_not_file(self):
        (self.root / 'folder').mkdir()
        self.assertEqual(self.status('folder'), 'NOT_A_FILE')

    def test_parent_traversal_rejected(self):
        self.assertEqual(self.status('../outside'), 'PATH_REJECTED')

    def test_absolute_path_rejected(self):
        self.assertEqual(self.status(str(self.root / 'sample.txt')), 'PATH_REJECTED')

    def test_windows_absolute_path_rejected(self):
        self.assertEqual(self.status('C:\\outside.txt'), 'PATH_REJECTED')

    def test_symlink_escape_rejected(self):
        link = self.root / 'escape'
        try:
            link.symlink_to(self.root.parent, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation unavailable')
        self.assertEqual(self.status('escape/outside'), 'PATH_REJECTED')

    def test_invalid_hash_rejected(self):
        self.assertEqual(self.status('sample.txt', 'not-a-digest'), 'INVALID_MANIFEST_ENTRY')

    def test_empty_manifest_rejected(self):
        with self.assertRaises(ValueError):
            check.verify_files(self.root, {})

    def test_read_failure_reported(self):
        with mock.patch.object(check, 'sha256', side_effect=PermissionError):
            self.assertEqual(self.status('sample.txt'), 'READ_ERROR')

    def test_no_file_changes(self):
        before = (self.root / 'sample.txt').read_bytes()
        self.status('sample.txt')
        self.assertEqual((self.root / 'sample.txt').read_bytes(), before)


class ModeChecks(unittest.TestCase):
    def test_exit_codes(self):
        self.assertEqual(check.exit_code(True, False), 0)
        self.assertEqual(check.exit_code(True, True), 2)
        self.assertEqual(check.exit_code(False, False), 1)
        self.assertEqual(check.exit_code(False, True), 1)

    def test_live_request_cannot_enable_orders(self):
        report = {'baseline_files_verified': True, 'status': 'FILES_VERIFIED_LIVE_NOT_IMPLEMENTED', 'live_order_submission': False}
        with mock.patch.object(check, 'inspect_installation', return_value=report), mock.patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = check.main(['--require-live'])
        self.assertEqual(code, 2)
        data = json.loads(output.getvalue())
        self.assertEqual(data['status'], 'LIVE_NOT_IMPLEMENTED')
        self.assertIs(data['live_order_submission'], False)

    def test_nonexistent_live_flag_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            check.main(['--live'])
        self.assertEqual(exc.exception.code, 2)

    def test_missing_installation_fails(self):
        with tempfile.TemporaryDirectory() as empty, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check.main(['--repo-root', empty]), 1)

    def test_current_baseline_passes_without_network(self):
        with mock.patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            result = check.inspect_installation(HERE.parent)
        self.assertTrue(result['baseline_files_verified'])
        self.assertFalse(result['live_order_submission'])


if __name__ == '__main__':
    unittest.main()
