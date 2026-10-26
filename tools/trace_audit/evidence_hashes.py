"""Read-only file identity checks; identity is separate from semantic validity."""
import hashlib
from pathlib import Path
import re


def resolve_reference(base, name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('empty or non-string reference')
    path = Path(name.replace('\\', '/'))
    if path.is_absolute():
        return path.resolve()
    if path.drive or path.root:
        raise ValueError('ambiguous drive/root-relative reference')
    base = Path(base).resolve()
    resolved = (base / path).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError('relative reference escapes its declared base')
    return resolved


class FileAudit:
    def __init__(self):
        self.cache = {}

    def identity(self, path):
        path = Path(path).resolve()
        before = path.stat()
        key = (str(path), before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        if key not in self.cache:
            with path.open('rb') as stream:
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('file changed during hashing')
            self.cache[key] = {'sha256': sha, 'bytes': after.st_size}
        return {'path': str(path), **self.cache[key]}

    def check(self, base, name, expectation, role, field):
        row = {'field': field, 'role': role, 'reference': name}
        try:
            path = resolve_reference(base, name)
            row['path'] = str(path)
            if isinstance(expectation, str):
                expectation = {'sha256': expectation}
            if not isinstance(expectation, dict):
                raise ValueError('expectation must be a digest or metadata object')
            sha = expectation.get('sha256')
            size = expectation.get('bytes', expectation.get('size'))
            if sha is not None and (not isinstance(sha, str) or not re.fullmatch('[0-9a-fA-F]{64}', sha)):
                raise ValueError('invalid SHA256 expectation')
            if size is not None and (type(size) is not int or size < 0):
                raise ValueError('invalid byte-count expectation')
            row['expected_sha256'] = sha
            row['expected_bytes'] = size
            row['actual'] = self.identity(path)
            if sha is None:
                row['status'] = 'snapshot_only'
            elif (sha.lower() == row['actual']['sha256'] and
                  (size is None or size == row['actual']['bytes'])):
                row['status'] = 'match'
            else:
                row['status'] = {'source': 'source_drift', 'document': 'document_drift',
                                 'binary': 'build_drift'}.get(role, 'evidence_mismatch')
        except FileNotFoundError:
            row['status'] = 'missing'
        except (OSError, ValueError, TypeError) as exc:
            row.update(status='invalid_reference', error=str(exc))
        return row


def is_error(row):
    return row['status'] in {'missing', 'invalid_reference', 'evidence_mismatch'}
