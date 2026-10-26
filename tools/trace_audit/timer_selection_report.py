"""Publish native selected-timer replay with before/after and current-build evidence."""
import argparse
import difflib
import json
from pathlib import Path

from .rng_probe import digest
from .selected_timer_replay import compile_plan

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args(); folder = args.folder.resolve()
    tests = json.loads((folder / 'all-tests-final-result.json').read_text('utf-8'))
    replay = json.loads((folder / 'replay/result.json').read_text('utf-8'))
    before = json.loads((folder / 'before.json').read_text('utf-8'))
    examples = json.loads((folder / 'examples/result.json').read_text('utf-8'))
    parity = json.loads((folder / 'after-async/result.json').read_text('utf-8'))
    baseline = json.loads((folder / 'replay-comparison.json').read_text('utf-8'))
    if not tests['passed'] or not examples['passed'] or not parity['passed'] or not baseline['cases_identical']:
        raise ValueError('validation incomplete')
    if len(replay['runs']) != 4 or len(replay['controls']) != 2 or not replay['passed']:
        raise ValueError('selected replay incomplete')
    for name in ('core', 'calls'):
        plan = compile_plan(ROOT / 'artifacts/timer-identity-20261024', name)
        published = json.loads((folder / 'replay' / (name + '-plan.json')).read_text('utf-8'))
        if plan != published: raise ValueError('persisted trace plan differs')
        for run in [r for r in replay['runs'] if r['capture_case'] == name]:
            if not run['passed'] or run['mapped_timers'] != 4 or run['final']['events'] != plan['final_labels']:
                raise ValueError('selected output differs')
            if [s['command'] for s in run['steps']] != plan['commands']:
                raise ValueError('runtime did not consume recorded commands')
    for run in replay['controls']:
        if not run['passed'] or run['final']['events'][2:4] != ['timer-b', 'timer-a']:
            raise ValueError('selected order control ineffective')
    for name, key in [('dist/js.exe', 'shell_sha256'), ('dist/ruyijs_client.dll', 'client_sha256')]:
        if digest(ROOT / name) != replay[key]: raise ValueError('runtime identity changed')
    lines = ['# 从静态timer记录驱动ruyijs原生任务选择', '',
        '本轮已实现显式宿主timer选择，并在实际shell与C DLL上验证。两份Firefox',
        '记录转换为任务计划，经Python/C共四次执行完全一致；反转首两个就绪timer',
        '的两次对照确实改变输出，证明宿主选择控制了原队列执行。完整原网页闭环、',
        'Worker/消息选择及精确历史时钟仍未完成。', '',
        '## 唯一owner与接口', '',
        'EventLoopAggregate保留唯一任务队列/时钟，Scheduling State保留原callback、',
        'realm和公开handle。Model查询原task，Claim可接收经过校验的任务ID，Invoke/',
        'Complete及原引擎微任务检查点完成实际执行。页面API、原型、receiver规则、',
        '字符串handler和参数roots保持既有实现。新入口只在宿主RPC，默认未开启。', '',
        '| Python接口 / event_loop action | 行为 |', '|---|---|',
        '| configure_timer_replay(enabled=True) | 首次页面执行前启用；请求字段严格校验 |',
        '| pending_timers() | 返回活跃公开timeout/interval的task_id、realm_id、handle、firings、due_ms、ready |',
        '| run_timer(task_id, expected_firings, at_ms) | 校验并执行一个指定timer，随后运行原引擎jobs |', '',
        'realm_id为当前Context既有publicHandles表的1起始身份，task_id为原队列ID。',
        '它们不是Firefox global/async ID；回放必须建立并核验对应关系。反复读取pending',
        '不执行timer，列表不暴露内部消息/rAF/idle/scheduler任务。Worker独立队列不在范围。', '',
        '## 选择前的验证', '',
        '要求Window owner、启用回放、logical clock、live public timer、未退休global、',
        '预期执行次数相等及任务已到期。at_ms是当前owner绝对elapsed，须单调且单次',
        '推进至多一天、epoch+at在精确范围。存在已知待处理microtask或external work',
        '时拒绝选择。参数、未知字段或状态验证失败时不移动时钟、不运行timer。', '',
        '验证成功才设置时间并Claim原任务；一项成功请求执行一个宏任务及其后的引擎',
        '微任务。其它宏任务保留。回调抛错会经过原异常捕获以RPC错误返回，其已发生',
        '副作用和微任务不会回滚；消费方应重新观察状态，避免重复执行已消耗次数。', '',
        '显式模式允许从多个已就绪timer中选择次序，也可将时间推进到所选deadline。',
        '它不自行证明该次序满足所有网页因果约束；记录计划的完整性仍由上游负责。', '',
        '## 静态记录到执行', '',
        '输入是上一轮timer-identity/probe的core与calls捕获。编译器重新校验原文件',
        'hash、timer生命周期唯一关联及原async_mapping.js源码。五个注册中一个',
        '取消；四个fire的async/execution ID各自定位输出组。计划保留原身份、公开',
        'handle和执行序号；运行时在单一已知main realm中匹配这些handle，固定映射到',
        '原生task ID。每次选择前要求timer存在、未取消且firings与记录一致。', '',
        '两份计划×两接口，共四次、十六个实际timer选择，得到完整输出：', '',
        '`start → registered → timer-a → timer-b → resolve-before → resolve-after → reaction → finish`', '',
        'Promise反应由原微任务检查点执行，宿主没有直接调用回调或回写结果。',
        '两个对照交换timer-a/timer-b的命令顺序，输出也交换；它是控制能力验证，',
        '不冒充原trace回放成功。其余timer、Promise和完成状态仍按对应命令验证。', '',
        '本例按运行时due_ms推进，执行时刻0/0/20/40ms；未恢复Firefox墙钟耗时。',
        '源码先在空白本地页面求值以保留宿主检查边界，因此不包含原HTML加载调度',
        '复现。跨realm对应仅在通用接口测试中核验，没有宣称跨frame trace映射已完成。', '',
        '## 测试、构建和默认行为', '',
        f"完整{tests['tests']}项Python/实际C DLL测试通过，新增20项双接口检查。",
        '覆盖真实逆序选择、提前执行/错ID/旧firings/未知字段的原子拒绝、取消、退休、',
        '同号handle不同realm、interval自取消、string/GC/参数对象、native surface、',
        '非法receiver、内部消息/rAF保留、系统时钟拒绝、嵌套timer和异常后继续。',
        '普通模式仍按原FIFO执行。修改前后的24次同步本地trace回放结果相同，两个',
        '接口的15步异步fixture保持；11个示例语法及--help入口通过。', '',
        '实际shell已重编译链接；实际C客户端DLL也另行重新链接并经过真实调用。',
        '首次构建缺jsapi.h，修复后构建工具还需显式LLVM路径；失败日志均保留。',
        '首轮完整测试只有新增异常断言与原RPC语义不同，修正为期望错误后320项全过。', '',
        '## 复现', '', '```powershell',
        'Set-Location D:\\BaiduNetdiskDownload\\ivv8\\ivv8\\ruyijs',
        'python -B tools/build.py --jobs 12 --toolchain-bin C:/Users/Administrator/.mozbuild/clang/bin',
        'python -B -m unittest discover -s tests -p test_timer_selection.py -v',
        'python -B -m tools.trace_audit.selected_timer_replay artifacts/timer-identity-20261024 --output artifacts/selected-timer-new',
        '```', '',
        '调用示例：', '', '```python', 'ctx.configure_clock("logical", epoch_ms=1700000000000)',
        'ctx.configure_timer_replay(True)', 'ctx.eval("setTimeout(() => { window.finished = true; }, 10)")',
        'task = ctx.pending_timers()[0]', 'ctx.run_timer(task["task_id"], task["firings"], task["due_ms"])', '```', '',
        '## 身份和剩余验收', '',
        'shell：`'+replay['shell_sha256']+'`。', 'C DLL：`'+replay['client_sha256']+'`。',
        '验证清单：artifacts/timer-selection-20261024/validation.json。',
        '旧build/报告不覆盖，新源码与二进制归本轮；Firefox构建沿上一轮不变。', '',
        '原历史网页没有新增timer关联字段，尚需其它来源或新采集；完整跨realm/消息/',
        'Worker/外部I/O任务计划、ready-state一致性及业务结果仍缺。零性能影响与',
        '绝对不可观察同样未证明，本轮不是新的采集性能试验。', '']
    (folder / 'TIMER_SELECTION.md').write_text('\n'.join(lines), 'utf-8')
    sources = [name for name in before if not name.startswith('dist/')]
    sources += ['src/execution_scheduling/timer_selection.cpp', 'src/runtime/timer_selection.cpp',
                'tests/test_timer_selection.py', 'tools/trace_audit/selected_timer_replay.py', 'tools/trace_audit/timer_selection_report.py']
    diffs = []
    for name in sources:
        old = folder / 'before' / name
        diffs.extend(difflib.unified_diff(old.read_text('utf-8').splitlines(True) if old.exists() else [],
                    (ROOT / name).read_text('utf-8').splitlines(True), fromfile='before/' + name, tofile='after/' + name))
    (folder / 'implementation.diff').write_text(''.join(diffs), 'utf-8')
    reports = ['before.json', 'before-checks.json', 'before-replay/result.json', 'after-replay/result.json',
        'after-async/result.json', 'after-checks.json', 'replay-comparison.json', 'replay/result.json',
        'replay/core-plan.json', 'replay/calls-plan.json', 'examples/result.json', 'all-tests-result.json',
        'all-tests.log', 'all-tests-final-result.json', 'all-tests-final.log', 'build-runtime.json',
        'build-final.log', 'build-final-result.json', 'relink-client.log', 'relink-client-result.json',
        'implementation.diff', 'TIMER_SELECTION.md']
    manifest = {'schema': 'local.timer-selection-report.v1', 'tests': tests, 'full_goal_complete': False,
                'runtime': {key: replay[key] for key in ('shell_sha256', 'client_sha256')},
                'sources': {name: digest(ROOT / name) for name in sources},
                'reports': {name: digest(folder / name) for name in reports},
                'selected_replays': 4, 'reorder_controls': 2, 'default_replay_preserved': True}
    (folder / 'validation.json').write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    print(json.dumps({'published': True, 'tests': tests['tests'], 'runtime': manifest['runtime']}))


if __name__ == '__main__': main()
