"""Explicit path-base adapters for the preserved 20261024 experiment manifests."""
from pathlib import Path

BUILD_NAMES = {'shell': 'shell', 'shell_sha256': 'shell', 'restored_shell_sha256': 'shell',
               'js.exe': 'shell', 'client_sha256': 'client', 'restored_client_sha256': 'client',
               'c_dll': 'client', 'ruyijs_client.dll': 'client', 'firefox': 'firefox',
               'firefox_sha256': 'firefox', 'xul': 'xul', 'xul_sha256': 'xul'}


def references(data, manifest, workspace, firefox, project, outputs=None, inputs=None):
    """Yield (base, path, expectation, role, field); do not infer by file existence."""
    parent = manifest.parent
    groups = {'sources': (workspace, 'source'), 'firefox_sources': (firefox, 'source'),
              'reports': (parent, 'evidence'), 'experiments': (parent, 'evidence'),
              'outputs': (outputs or parent, 'evidence'), 'documents': (project, 'document')}
    if inputs is not None:
        groups['inputs'] = (inputs, 'source')
    for section, (base, role) in groups.items():
        items = data.get(section, {})
        if not isinstance(items, dict):
            raise ValueError(f'{section}: expected an object')
        for key, value in items.items():
            name = value.get('path', key) if isinstance(value, dict) else key
            item_role = 'document' if role == 'source' and Path(name).suffix.lower() == '.md' else role
            yield base, name, value, item_role, section + '.' + key
    for index, value in enumerate(data.get('raw_evidence_files', [])):
        if not isinstance(value, dict) or 'path' not in value:
            raise ValueError('raw_evidence_files: missing path')
        yield parent, value['path'], value, 'evidence', f'raw_evidence_files[{index}]'
    if 'input_sha256' in data:
        yield workspace, data['input'], data['input_sha256'], 'evidence', 'input_sha256'
    if 'measurement_selection_sha256' in data:
        base = parent if manifest.name == 'validation.json' else parent.parent
        yield base, 'measurement-selection.json', data['measurement_selection_sha256'], 'evidence', 'measurement_selection_sha256'
    builds = {'shell': workspace / 'dist/js.exe', 'client': workspace / 'dist/ruyijs_client.dll',
              'firefox': firefox / 'obj-jscall-check/dist/bin/firefox.exe',
              'xul': firefox / 'obj-jscall-check/dist/bin/xul.dll'}
    for section, items in [('', data)] + [(s, data.get(s, {})) for s in ('binaries', 'runtime', 'stable_runtime')]:
        for key, value in items.items():
            if key not in BUILD_NAMES:
                continue
            path = value.get('path', str(builds[BUILD_NAMES[key]])) if isinstance(value, dict) else str(builds[BUILD_NAMES[key]])
            yield workspace, path, value, 'binary', (section + '.' if section else '') + key


def catalog(workspace, project):
    names = ['html-dir', 'random-replay', 'crypto-replay', 'timer-handles', 'interval-trace',
             'object-snapshot', 'rng-trace', 'navigation-observer', 'navigation-replay',
             'rtc-order', 'call-alignment', 'tier-cost', 'tier-integrity', 'async-proof', 'concurrent-proof']
    entries = [(workspace / f'artifacts/{name}-20261024/validation.json', {}) for name in names]
    entries += [(workspace / 'artifacts/capture-cost-20261024/report/manifest.json', {}),
                (workspace / 'artifacts/tier-cost-20261024/final-report/manifest.json', {}),
                (workspace / 'artifacts/date-replay-20261024/restoration.json', {}),
                (project / 'work/reproduce-20261024-manifest.json', {'inputs': project})]
    for path, options in entries:
        if path == workspace / 'artifacts/tier-cost-20261024/validation.json':
            options['outputs'] = path.parent / 'final-report'
        yield path, options


def supplemental(workspace):
    """These reports carry build identities absent from their parent manifest."""
    return [workspace / name for name in (
        'artifacts/capture-cost-20261024/final/results.json',
        'artifacts/tier-cost-20261024/final/results.json',
        'artifacts/tier-integrity-20261024/native-replay-types/result.json')]
