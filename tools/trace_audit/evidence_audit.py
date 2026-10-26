"""Audit preserved experiment file identities without repeating online experiments."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from .evidence_hashes import FileAudit, is_error
from .evidence_refs import catalog, references, supplemental

ROOT = Path(__file__).resolve().parents[2]


def audit_manifest(auditor, path, workspace, firefox, project, **options):
    report = {'manifest': str(path), 'references': [], 'identity_scope': 'current snapshot, not origin authentication'}
    try:
        report['identity'] = auditor.identity(path)
        data = json.loads(path.read_text('utf-8-sig'))
        report['declared_schema'] = data.get('schema')
        report['unhashed_top_level_fields'] = sorted(set(data) - {
            'sources', 'firefox_sources', 'reports', 'experiments', 'outputs', 'documents', 'inputs',
            'raw_evidence_files', 'input', 'input_sha256', 'measurement_selection_sha256',
            'binaries', 'runtime', 'stable_runtime', 'shell_sha256', 'client_sha256',
            'restored_shell_sha256', 'restored_client_sha256', 'xul_sha256', 'firefox_sha256'})
        for args in references(data, path, workspace, firefox, project, **options):
            report['references'].append(auditor.check(*args))
        if auditor.identity(path) != report['identity']:
            raise ValueError('manifest changed while audit was running')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        report['error'] = str(exc)
    report['counts'] = dict(Counter(row['status'] for row in report['references']))
    report['identity_errors'] = sum(is_error(row) for row in report['references']) + int('error' in report)
    return report


def markdown(result):
    lines = ['# 实验证据身份审计', '', f"审计时间：{result['created_utc']}。", '',
             '本报告重新读取历史清单所列文件的字节，核对SHA256和已声明大小。',
             'match只表示这些字节与该清单一致；清单自身由本次快照标识，未作签名或来源认证。',
             '未递归核验任意JSON里的路径，也未重新执行所有语义校验器。完整目标仍未完成。', '',
             '| 清单/身份补充报告 | 引用数 | 字节一致 | 源码变化 | 文档变化 | 构建变化 | 错误 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for item in result['manifests']:
        path = Path(item['manifest'])
        label = '/'.join(path.parts[-3:])
        c = item['counts']
        lines.append(f"| {label} | {len(item['references'])} | {c.get('match', 0)} | "
                     f"{c.get('source_drift', 0)} | {c.get('document_drift', 0)} | "
                     f"{c.get('build_drift', 0)} | {item['identity_errors']} |")
    lines += ['', '计数按引用计，同一文件可能被多份清单引用；不视为独立实验次数。', '',
              '## 本次统计', '', '```json', json.dumps(result['counts'], indent=2), '```', '',
              '## 状态解释', '',
              '- match：存在历史摘要且当前字节一致；语义范围仍以原实验为准。',
              '- source_drift/document_drift/build_drift：工作路径已不同于历史版本；保留两份摘要，历史结果不冒充当前重测。',
              '- evidence_mismatch/missing/invalid_reference：证据引用错误，应逐项调查，进程返回非零。',
              '- snapshot_only：文件存在但没有历史摘要，当前摘要仅供后续定位。', '',
              '## 全部非匹配项', '']
    for item in result['manifests']:
        if 'error' in item:
            lines.append(f"- 清单读取错误：`{item['manifest']}`：{item['error']}")
        for row in item['references']:
            if row['status'] != 'match':
                lines.append(f"- **{row['status']}**：`{row['path'] if 'path' in row else row['reference']}` "
                             f"（`{Path(item['manifest']).parent.name}`，`{row['field']}`）。")
    lines += ['', '逐项历史/当前摘要和绝对路径见同目录audit.json。未读取文件正文进入公开报告。',
              '失败的时钟实验仅核对恢复构建；failed_shell_sha256及恢复布尔量不是已通过回放证据。',
              '早期无逐文件摘要的清单仅覆盖其显式构建身份；零引用不表示其原始日志已校验。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=ROOT)
    parser.add_argument('--project', type=Path, default=Path('D:/cf-turnstile-scrapingcourse'))
    parser.add_argument('--firefox', type=Path, default=Path('D:/firefox/src/firefox'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workspace, project, firefox = (p.resolve() for p in (args.workspace, args.project, args.firefox))
    args.output.mkdir(parents=True, exist_ok=False)
    auditor = FileAudit()
    manifests = [audit_manifest(auditor, path, workspace, firefox, project, **opts)
                 for path, opts in catalog(workspace, project)]
    manifests += [audit_manifest(auditor, path, workspace, firefox, project) for path in supplemental(workspace)]
    rows = [row for item in manifests for row in item['references']]
    result = {'schema': 'local.evidence-identity-audit.v1',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'manifests': manifests,
              'counts': dict(Counter(row['status'] for row in rows)),
              'identity_errors': sum(item['identity_errors'] for item in manifests),
              'unique_files_read': len({key[0] for key in auditor.cache}),
              'full_goal_complete': False, 'semantic_experiments_rerun': False,
              'sources': [auditor.identity(Path(__file__).with_name(name)) for name in (
                  'evidence_hashes.py', 'evidence_refs.py', 'evidence_audit.py')]}
    (args.output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    (args.output / 'AUDIT.md').write_text(markdown(result), 'utf-8')
    print(json.dumps({key: result[key] for key in ('counts', 'identity_errors', 'unique_files_read', 'full_goal_complete')}))
    return int(bool(result['identity_errors']))


if __name__ == '__main__':
    raise SystemExit(main())
