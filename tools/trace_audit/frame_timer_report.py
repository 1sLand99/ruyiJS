"""Publish explicit realm-binding evidence and preserved cross-frame timer replay."""
import argparse
import difflib
import json
from pathlib import Path

from .frame_timer_plan import compile_plan
from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('folder', type=Path)
    args = parser.parse_args(); folder = args.folder.resolve()
    report = json.loads((folder / 'replay/result.json').read_text('utf-8'))
    tests = json.loads((folder / 'all-tests-result.json').read_text('utf-8'))
    regressions = json.loads((folder / 'regressions.json').read_text('utf-8'))
    examples = json.loads((folder / 'examples/result.json').read_text('utf-8'))
    comparison = json.loads((folder / 'selection-comparison.json').read_text('utf-8'))
    if not tests['passed'] or any(r['returncode'] for r in regressions) or not examples['passed']:
        raise ValueError('validation incomplete')
    if comparison != {'runs_equal': True, 'controls_equal': True}:
        raise ValueError('prior selected replay baseline changed')
    plan = compile_plan(ROOT / 'artifacts/timer-identity-20261024')
    saved = json.loads((folder / 'replay/plan.json').read_text('utf-8'))
    if plan != saved or digest(folder / 'replay/plan.json') != report['plan_sha256']:
        raise ValueError('published frame plan differs from preserved trace')
    if len(report['runs']) != 4 or len(report['controls']) != 2 or not report['passed']:
        raise ValueError('frame execution cases incomplete')
    for run in report['runs']:
        if not run['passed'] or len(run['steps']) != 7 or run['final'] != plan['final_page']:
            raise ValueError('cross-frame output differs')
        if [s['command'] for s in run['steps']] != plan['commands']:
            raise ValueError('recorded command sequence not consumed')
        if len(set(run['bindings'].values())) != 4:
            raise ValueError('frame binding conflated')
    for adapter in ('Python', 'C'):
        runs = [r for r in report['runs'] if r['adapter'] == adapter]
        if runs[0]['bindings'] == runs[1]['bindings']:
            raise ValueError('reverse binding control did not vary local IDs')
    if any(not r['rejected_as_expected'] or len(r['steps']) != 1 for r in report['controls']):
        raise ValueError('wrong frame binding was accepted')
    for name, key in [('dist/js.exe', 'shell_sha256'), ('dist/ruyijs_client.dll', 'client_sha256')]:
        if digest(ROOT / name) != report[key]: raise ValueError('current runtime differs')
    lines = ['# 跨frame timer回放：明确realm映射、重复handle与文档退休', '',
        '本轮在原Scheduling owner上新增宿主timer_realm查询，保留原窗口和timer对象。',
        '已保存的Firefox多frame记录通过Python/C四次回放，各消费七次timer执行，',
        '包含三个interval tick、字符串回调和移除frame的取消。反向绑定改变实际',
        'realm编号但保持结果；错误交换两个frame绑定的两次对照均在首个输出失败。',
        '完整原网页业务闭环、Worker/消息调度与零性能影响目标仍未完成。', '',
        '## 为什么显式绑定', '',
        '同一个文档内，两个frame和主页面都可能返回public_handle=1。Firefox',
        'global_id与ruyijs realm_id属于不同命名空间；编号相同不表示同一窗口。',
        '现有捕获中contentWindow返回为Proxy且nativeId为0，直接按此getter返回值',
        '拼接身份没有证据。本轮限定原样fixture，使用已记录注册调用的源码行/列',
        '确认frame0/frame1/main/removed角色，源码及HTML资源hash先核对。', '',
        '该源码位置适配器不是通用DOM拓扑恢复。它额外要求每个角色恰好对应一个',
        '捕获global，每个global仅对应一个角色，实际timer DOM调用与注册nativeId/',
        'handle/context唯一连接。输出label不参与选择角色。', '',
        '## 宿主Window身份查询', '',
        '`timer_realm(target="window")`沿既有EvaluateHostExpression在当前主页面',
        '求值，再由Scheduling检查结果恰好是已安装且未退休的Window global。',
        '返回/预留原publicHandles表内身份，不消耗timer handle或task ID。',
        '因此可在注册前绑定第三个frame，随后原脚本移除该frame时验证其timer退出。', '',
        '查询要求提前启用timer replay；字段、字符串类型与1..65536 UTF-16长度',
        '先检查，然后冻结配置并执行表达式。它是显式宿主求值，表达式可能有副作用',
        '或抛错，未承诺纯读取/回滚。仅解开引擎CCW，不解析用户Proxy内部，不通过',
        '任意对象的所属realm冒充Window。定制跨源WindowProxy视图目前不在合同内。', '',
        '## 记录与运行时的对应', '',
        '真实记录包含4个global、6个timer注册；5个timer执行共7次，另一个因frame',
        '移除而clear_all。三个活跃global的handle=1保持独立；interval的三次执行',
        '始终映射同一个native task，firings依次0/1/2，最后由原clearInterval取消。', '',
        '| 角色 | 正向预绑定realm ID | 反向预绑定realm ID |', '|---|---:|---:|']
    standard, reverse = report['runs'][0], report['runs'][1]
    for role in ('main', 'frame0', 'frame1', 'removed'):
        lines.append(f"| {role} | {standard['bindings'][role]} | {reverse['bindings'][role]} |")
    lines += ['', '两种编号分配顺序均得到：', '', '`a → b → string → tick-1 → tick-2 → tick-3 → end`', '',
        '每次命令由捕获的global角色+公开handle查实际待执行任务，再核对稳定task ID',
        '及firings，调用已有run_timer。下一时刻取当前owner期限，不恢复历史墙钟。',
        '选择前后都要求removed realm无待执行timer，最终所有公开timer耗尽且页面',
        'done/errors/handles/events与捕获一致。未用选择回调源码或写期望数组替代执行。', '',
        '## 字符串handler的嵌套执行根', '',
        '字符串timer的marker并不直接处于fire execution ID，而在新的script_root。',
        '编译器沿其parent_execution_context_id回到timer fire，保留完整身份链；',
        '绝不使用“前一行fire”或最近时间戳。错误父ID、错session、循环、重复fire',
        '或跨文件全序假设均由负例检查。该结果也说明仅比较async_context_id会漏掉',
        '合法嵌套脚本执行。', '',
        '## 实际验证', '',
        f"完整{tests['tests']}项测试通过，新增12项Python/真实C DLL身份查询检查和7项离线祖先链负例。",
        '实际重建shell并重新链接C DLL。四次跨frame回放包含28次timer选择；两个',
        '错误映射对照各在第一个任务输出b而期望a时停止。反向预绑定不是反转执行',
        '顺序，而是主动改变runtime realm编号以检验对应关系。', '',
        '原有单main realm四次回放及两个控制组与修改前逐字段相等；24次同步本地',
        'trace回放、默认15步异步样例和11个示例语法/CLI入口通过。示例入口检查不',
        '表示远程业务流程均已成功。Firefox沿上一构建，未重新采集目标网页。', '',
        '## 复现', '', '```powershell',
        'Set-Location D:\\BaiduNetdiskDownload\\ivv8\\ivv8\\ruyijs',
        'python -B tools/build.py --jobs 12 --toolchain-bin C:/Users/Administrator/.mozbuild/clang/bin',
        'python -B -m unittest discover -s tests -p test_timer_realm.py -v',
        'python -B -m tools.trace_audit.frame_timer_replay artifacts/timer-identity-20261024 --output artifacts/frame-timer-new',
        '```', '',
        '生成plan.json保存角色/原行/源码位置及timer/marker祖先链，result.json保存',
        '实际窗口绑定、每步task snapshot、输出、终态和错误对照。每次输出用新目录。', '',
        'Python查询示例：', '', '```python', 'ctx.configure_clock("logical", epoch_ms=1700000000000)',
        'ctx.configure_timer_replay(True)', 'ctx.load_page("http://localhost/", "<iframe></iframe>")',
        'main_id = ctx.timer_realm("window")',
        "frame_id = ctx.timer_realm(\"document.querySelector('iframe').contentWindow\")", '```', '',
        '## 身份与限制', '', 'shell：`'+report['shell_sha256']+'`。',
        'C DLL：`'+report['client_sha256']+'`。',
        '证据：artifacts/frame-timer-replay-20261024/validation.json。', '',
        '映射只适用于hash限定的同源frame样例；位置变化或歧义应停止编译。通用',
        '文档导航/替换生命周期、跨源WindowProxy、Worker与消息/外部I/O仍缺独立',
        '证明。本轮没有新性能测量，也未把观察接口位置推导为页面不可察觉。', '']
    (folder / 'FRAME_TIMER_REPLAY.md').write_text('\n'.join(lines), 'utf-8')
    before = json.loads((folder / 'before.json').read_text('utf-8'))
    sources = [name for name in before if not name.startswith('dist/')]
    sources += ['src/runtime/timer_realm.cpp', 'tests/test_timer_realm.py', 'tests/test_frame_timer_plan.py',
                'tools/trace_audit/frame_timer_plan.py', 'tools/trace_audit/frame_timer_replay.py', 'tools/trace_audit/frame_timer_report.py']
    diff = []
    for name in sources:
        old = folder / 'before' / name
        diff.extend(difflib.unified_diff(old.read_text('utf-8').splitlines(True) if old.exists() else [],
                    (ROOT / name).read_text('utf-8').splitlines(True), fromfile='before/' + name, tofile='after/' + name))
    (folder / 'implementation.diff').write_text(''.join(diff), 'utf-8')
    reports = ['before.json', 'before-selection/result.json', 'after-selection/result.json', 'selection-comparison.json',
        'build.log', 'build-result.json', 'build-runtime.json', 'relink-client.log', 'relink-client-result.json',
        'focused-tests.log', 'focused-tests-result.json', 'all-tests.log', 'all-tests-result.json', 'replay/plan.json',
        'replay/result.json', 'sync-replay/result.json', 'async-parity/result.json', 'regressions.json',
        'examples/result.json', 'implementation.diff', 'FRAME_TIMER_REPLAY.md']
    manifest = {'schema': 'local.frame-timer-report.v1', 'tests': tests, 'runtime': {k: report[k] for k in ('shell_sha256', 'client_sha256')},
                'sources': {name: digest(ROOT / name) for name in sources}, 'reports': {name: digest(folder / name) for name in reports},
                'full_goal_complete': False, 'positive_runs': 4, 'wrong_binding_controls': 2}
    (folder / 'validation.json').write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    print(json.dumps({'published': True, 'tests': tests['tests'], 'runtime': manifest['runtime']}))


if __name__ == '__main__': main()
