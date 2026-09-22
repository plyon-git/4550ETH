#!/usr/bin/env python3
"""Read-only baseline file check. No broker, credentials, network, or live mode."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REFERENCE_FILES = (
    'results/breakout_trades.csv.gz',
    'results/breakout_equity.csv.gz',
    'results/breakout_weeks.csv',
)


def confined_file(root: Path, relative: str) -> Path:
    """Reject absolute paths, traversal, and symlinks outside the repository."""
    rel = PurePosixPath(relative)
    if not relative or rel.is_absolute() or '..' in rel.parts or '\\' in relative or ':' in relative:
        raise ValueError('Unsafe relative path')
    base = root.resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base):
        raise ValueError('Path escapes repository')
    return candidate


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_files(root: Path, expected: dict[str, str]) -> list[dict[str, object]]:
    if not isinstance(expected, dict) or not expected:
        raise ValueError('Nonempty hash manifest required')
    rows = []
    for relative, wanted in expected.items():
        row: dict[str, object] = {'file': str(relative), 'status': 'UNCHECKED'}
        if not isinstance(relative, str) or not isinstance(wanted, str) or not re.fullmatch(r'[0-9a-f]{64}', wanted):
            row['status'] = 'INVALID_MANIFEST_ENTRY'
        else:
            try:
                path = confined_file(root, relative)
                if not path.exists():
                    row['status'] = 'MISSING'
                elif not path.is_file():
                    row['status'] = 'NOT_A_FILE'
                else:
                    actual = sha256(path)
                    row.update(status='OK' if actual == wanted else 'HASH_MISMATCH', sha256=actual)
            except ValueError:
                row['status'] = 'PATH_REJECTED'
            except OSError:
                row['status'] = 'READ_ERROR'
        rows.append(row)
    return rows


def inspect_installation(root: Path) -> dict[str, object]:
    expected = json.loads((HERE / 'PINNED_BASELINE_SHA256.json').read_text(encoding='utf-8'))
    checks = verify_files(root, expected)
    references = []
    for relative in REFERENCE_FILES:
        try:
            present = confined_file(root, relative).is_file()
        except (ValueError, OSError):
            present = False
        references.append({'file': relative, 'present': present})
    passed = all(row['status'] == 'OK' for row in checks) and all(row['present'] for row in references)
    versions = {}
    for package in ('numpy', 'pandas', 'numba'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        'baseline_files_verified': passed,
        'status': 'FILES_VERIFIED_LIVE_NOT_IMPLEMENTED' if passed else 'BASELINE_FILE_CHECK_FAILED',
        'checks': checks,
        'reference_files': references,
        'python_version': sys.version.split()[0],
        'installed_numerical_packages': versions,
        'live_order_submission': False,
        'baseline_model_type': 'deterministic_rules_no_trained_model',
        'requested_variant_packages_verified': {'60.37pct_52w': False, '102.02pct_93w': False},
        'scope': 'File identity and reference presence only. Run reproduce_saved.py for numerical reproduction. No live readiness certification.',
    }


def exit_code(files_ok: bool, require_live: bool) -> int:
    if not files_ok:
        return 1
    return 2 if require_live else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT, help='Working-copy root to inspect')
    parser.add_argument('--require-live', action='store_true', help='Check live support; always reports not implemented, never places orders')
    args = parser.parse_args(argv)
    try:
        report = inspect_installation(args.repo_root)
    except (OSError, ValueError, TypeError) as error:
        report = {'baseline_files_verified': False, 'status': 'BASELINE_FILE_CHECK_FAILED',
                  'error_type': type(error).__name__, 'live_order_submission': False}
    if args.require_live and report['baseline_files_verified']:
        report['status'] = 'LIVE_NOT_IMPLEMENTED'
    print(json.dumps(report, indent=2, allow_nan=False))
    return exit_code(bool(report['baseline_files_verified']), args.require_live)


if __name__ == '__main__':
    raise SystemExit(main())
