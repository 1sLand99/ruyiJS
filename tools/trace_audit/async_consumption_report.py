"""Publish the bounded checkpoint-consumption result and measured identity gap."""
import argparse
import json
from pathlib import Path

from .async_mapping_probe import inspect
from .async_evidence import load_rows
from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args(); folder = args.folder.resolve()
    report = json.loads((folder / 'verified/result.json').read_text('utf-8'))
    mapping = json.loads((folder / 'mapping/result.json').read_text('utf-8'))
    tests = json.loads((folder / 'offline-tests-final-result.json').read_text('utf-8'))
    if not report['passed'] or len(report['runs']) != 8 or len(report['negative_controls']) != 6 or not tests['passed']:
        raise ValueError('incomplete experiment')
    for name, expected in report['sources'].items():
        if digest(ROOT / name) != expected: raise ValueError('consumer source changed')
    for name, key in [('dist/js.exe', 'shell_sha256'), ('dist/ruyijs_client.dll', 'client_sha256')]:
        if digest(ROOT / name) != report[key]: raise ValueError('current runtime differs')
    if digest(Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/xul.dll')) != mapping['xul_sha256']:
        raise ValueError('current Firefox differs')
    if digest(Path(__file__).with_name('async_mapping.js')) != mapping['script_sha256']:
        raise ValueError('mapping workload changed')
    for entry in report['contracts']:
        if digest(folder / 'verified' / entry['path']) != entry['sha256']:
            raise ValueError('persisted checkpoint contract changed')
    for case in mapping['cases']:
        if case['mode'] == 'off': continue
        rows, sources = load_rows(folder / 'mapping' / case['mode'])
        actual = inspect(rows)
        if sources != case['sources'] or any(actual[key] != case[key] for key in actual):
            raise ValueError('mapping proof did not reproduce from raw records')
        if case['registrations'] != 5 or case['observed_timer_schedules'] != 4 or any(
                len(row['candidate_registration_lines']) != 5 for row in case['timer_join_candidates']):
            raise ValueError('mapping ambiguity differs')
        if case['promise_parent_markers'] != ['resolve-before', 'resolve-after']:
            raise ValueError('deferred promise provenance differs')
    steps = [len(row['steps']) for row in report['runs']]
    times = [row['steps'][-1]['after']['now_ms'] for row in report['runs']]
    lines = ['# 从异步 trace 消费执行边界：已通过范围与任务映射缺口', '',
        '本轮把四份保存的本地trace编译为九组观察约束，并通过ruyijs现有逐任务接口',
        '实时核对执行。Python/C共八次通过，六次故意破坏期望的运行均在首处分歧停止。',
        '它验证固定样例的观察边界一致性；尚未按trace身份选择待执行任务，完整原网页',
        '闭环和确定性全局调度仍未完成。', '',
        '## 输入与编译', '',
        '输入为async-proof-20261024/final-after的两轮core/calls捕获。先核对fixture',
        '源码hash，再验证schedule/resume、message、marker、writer及calls模式调用ID。',
        '每个marker从显式context向上沿queueMicrotask/Promise父边到script/timer/message',
        '根，生成观察组。组顺序取主页面同一文件中marker的实际次序，不用墙钟拼接线程。',
        '此处立即兑现Promise的归组假设由固定源码限定；普通Promise的注册上下文',
        '本身不保证其反应与注册操作属于同一检查点。', '',
        '| 组 | 实际marker |', '|---:|---|']
    contract = json.loads((folder / 'verified/contract-0-core.json').read_text('utf-8'))
    for index, group in enumerate(contract['groups']):
        lines.append(f"| {index} | {', '.join(group['labels'])} |")
    lines += ['', '## 原运行时执行与负对照', '',
        '本地HTTP服务和已有资源catalog提供原样源码。客户端仅配置已有logical clock、',
        '加载页面、注入原start脚本，并使用max_tasks=1逐步推进现有owner队列。每次',
        '推进读取fixture自身的结果数组，要求新增输出恰好匹配下一组；期望值未写回',
        '页面，回调未由宿主直接调用，页面API未被替换。', '',
        f'八次运行均消费九组、十五个marker。宿主推进步数{min(steps)}—{max(steps)}，',
        f'结束逻辑时间{min(times):g}—{max(times):g}ms；这已直接说明运行内部轮询不是确定的。',
        '每次advance的executed最多1，但独立Worker的内部执行不计入此预算。',
        '允许无新marker的内部任务，仍逐步记录；每次推进后等待5ms供Worker进程运行，',
        '总计最多8秒/2000步。该等待不是采集耗时，也没有恢复原trace时间。', '',
        '故意修改期望合同：交换start/microtask、把interval-3和其微任务complete拆成',
        '两组、删掉interval-2。三类在Python和C各运行一次，六次全部在对应checkpoint',
        '报错；没有容忍新增、遗漏、跨组输出或仅靠最终done判成功。', '',
        '## 真实Firefox反例：注册身份仍有歧义', '',
        '新增本地脚本在同一个registerSiblings调用中注册五个timeout，其中一个立即',
        '取消，四个实际执行；另创建pending Promise，由20ms timer兑现。off/core/calls',
        '三次页面输出一致。两个采集模式均有五次DOM setTimeout和四条已观察schedule。',
        '只按process/session/parent_execution_context_id和async_parent_call_id连接，',
        '每条schedule各有五个注册候选。开启jscall未消除此歧义：同一调用会注册多任务。',
        '这里证明现有共享ID键不充分；未声称已知回调源码永远不能提供附加推断。', '',
        '延迟Promise的schedule父上下文实际含resolve-before/resolve-after，因此本例',
        '关联到兑现它的timer，而非最初注册then的script。对应组为两个resolve marker',
        '加reaction。必须保留这个实测语义，勿把所有async父边都写成注册位置。', '',
        '## 优先改进与opcode判断', '',
        '1. 在现有异步owner记录注册身份与async_context_id的明确对应，并包含realm/',
        '   owner生命周期和任务种类。公共timer handle仅在所属global中有意义。',
        '2. 记录取消/退休/重复执行序号；明确从未观察到的任务与被取消任务的区别，',
        '   并对预算溢出及门控跨会话保留gap。记录开销需单独测量。',
        '3. 将Promise注册与实际入队/兑现来源分开，捕获足以区分任务与微任务检查点的身份。',
        '4. ruyijs消费这些身份前先验证原任务已就绪，再在已有owner中控制选择；Worker',
        '   需要协调进程输入及投递，不能以宿主轮询步数充当全局任务序号。',
        '5. opcode仅用于上述边界证据齐备后仍未解释的短窗口内部首分歧；它不替代',
        '   跨owner注册键。当前没有实现或测量opcode采集。', '',
        '以上为下一步设计要求，本轮尚未修改生产调度器或Firefox采集器。', '',
        '## 复现与验证', '', '```powershell',
        'Set-Location D:\\BaiduNetdiskDownload\\ivv8\\ivv8\\ruyijs',
        'python -B -m tools.trace_audit.async_contract_run artifacts/async-proof-20261024/final-after/result.json --output artifacts/async-contract-new',
        'python -B -m tools.trace_audit.async_mapping_probe --output artifacts/async-mapping-new',
        'python -B -m unittest discover -s tests -p test_async_contract.py -v', '```', '',
        f"本次五组离线测试共{tests['tests']}项通过，其中新增14项覆盖边界分组、消费负例和JSON往返。",
        '完整历史261项回归仍归属于其原轮次，本轮无生产代码变更。快速推进先导试验',
        '在120步内未等到Worker结果，其失败记录保留；paced先导与正式执行分别保存。',
        'Firefox反例已从原日志再次计算，与保存结果完全一致。初版重验发现计数器',
        '整数键落盘后变成JSON字符串键，现显式使用字符串并增加往返测试；原数据未改。', '',
        '证据：artifacts/async-consumption-20261024/validation.json。',
        '设计：docs/ASYNC_CONSUMPTION_DESIGN_20261024.md。',
        '二进制：shell `'+report['shell_sha256']+'`；C DLL `'+report['client_sha256']+'`。', '']
    (folder / 'ASYNC_CONSUMPTION.md').write_text('\n'.join(lines), 'utf-8')
    paths = list((folder / 'verified').glob('*.json')) + [folder / name for name in (
        'mapping/result.json', 'offline-tests-final-result.json', 'offline-tests-final.log', 'pilot.json',
        'pilot-paced.json', 'ASYNC_CONSUMPTION.md')]
    sources = ['tools/trace_audit/' + name for name in ('async_contract.py', 'async_consume.py',
        'async_contract_run.py', 'async_mapping.js', 'async_mapping_probe.py', 'async_consumption_report.py')]
    sources += ['tests/test_async_contract.py', 'docs/ASYNC_CONSUMPTION_DESIGN_20261024.md']
    raw = [entry for case in mapping['cases'] for entry in case.get('sources', [])]
    manifest = {'schema': 'local.async-consumption-report.v1', 'tests': tests, 'positive_runs': 8,
                'negative_runs': 6, 'groups_per_run': 9, 'runtime': {k: report[k] for k in ('shell_sha256', 'client_sha256')},
                'xul_sha256': mapping['xul_sha256'], 'sources': {name: digest(ROOT / name) for name in sources},
                'reports': {str(path.relative_to(folder)): digest(path) for path in paths},
                'raw_evidence_files': raw, 'deterministic_task_replay': False, 'full_goal_complete': False}
    (folder / 'validation.json').write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    print(json.dumps({'published': True, 'tests': tests['tests'], 'raw_files': len(raw), 'full_goal_complete': False}))


if __name__ == '__main__': main()
