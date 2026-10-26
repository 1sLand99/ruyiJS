"""Publish validated timer lifecycle joins, costs and exact artifact identities."""
import argparse
import csv
import difflib
import json
from pathlib import Path
import statistics

from .async_evidence import load_rows
from .rng_probe import digest
from .timer_lifecycle import prove_timers

ROOT = Path(__file__).resolve().parents[2]
FIREFOX = Path('D:/firefox/src/firefox')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args(); folder = args.folder.resolve()
    probe = json.loads((folder / 'probe/result.json').read_text('utf-8'))
    cost = json.loads((folder / 'cost/result.json').read_text('utf-8'))
    tests = json.loads((folder / 'offline-tests-result.json').read_text('utf-8'))
    regressions = json.loads((folder / 'regressions.json').read_text('utf-8'))
    enabled = json.loads((folder / 'enabled-async/result.json').read_text('utf-8'))
    if not tests['passed'] or any(r['returncode'] for r in regressions) or len(regressions) != 4:
        raise ValueError('regressions incomplete')
    if len(probe['cases']) != 7 or len(cost['runs']) != 9 or not enabled['passed']:
        raise ValueError('probe/cost incomplete')
    xul = digest(FIREFOX / 'obj-jscall-check/dist/bin/xul.dll')
    if any(r['xul_sha256'] != xul for r in (probe, cost, enabled)):
        raise ValueError('capture build identity differs')
    for case in probe['cases']:
        rows, sources = load_rows(folder / 'probe' / case['name'])
        if sources != case['sources']: raise ValueError('probe capture file changed')
        if 'proof' in case and prove_timers(rows) != case['proof']:
            raise ValueError('lifecycle proof changed')
    rows, sources = load_rows(folder / 'enabled-async')
    if sources != enabled['sources'] or prove_timers(rows) != enabled['timers']:
        raise ValueError('enabled async evidence changed')
    for run in cost['runs']:
        rows, sources = load_rows(folder / 'cost' / f"{run['round']}-{run['mode']}")
        if sources != run['sources']: raise ValueError('cost capture file changed')
        if run['mode'] == 'timers':
            proof = prove_timers(rows)
            if proof['phases'] != {'register': 6200, 'cancel': 6200}:
                raise ValueError('cost timer coverage differs')
    with (folder / 'measurements.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream); writer.writerow(['round', 'mode', 'sample', 'registrations', 'page_ms', 'checksum'])
        for run in cost['runs']:
            for index, sample in enumerate(run['page']['samples']):
                writer.writerow([run['round'], run['mode'], index, sample['count'], sample['ms'], sample['checksum']])
    increment = statistics.median(cost['paired_timer_vs_core'])
    core_ratio = statistics.median(cost['paired_core_vs_off'])
    lines = ['# 原生 Window timer 身份：注册、取消与实际执行的唯一关联', '',
        '本轮已改进Firefox采集器并构建实际xul。同一函数注册多个timer的歧义得到',
        '明确ID关联，取消和文档移除也有生命周期证据。新增记录默认关闭，需显式启用；',
        '密集timer样例测得明显成本。原历史capture保持原样，完整ruyijs网页闭环仍未完成。', '',
        '## 已实现的数据关系', '',
        'TimeoutManager仍管理公开handle与任务生命周期；既有TimeoutHandler异步registry',
        '继续提供async_context_id。新timer_lifecycle将二者关联到process/session、',
        'WindowID、canonical nativeId、当前execution/call及转换后的请求delay。',
        'register发生在实际注册成功之后；fire/finish位于原async resume scope内；',
        'cancel仅在找到待取消任务时输出；clear_all来自原文档清理遍历。', '',
        '身份链为：DOM setTimeout/Interval的接收者nativeId+返回handle+执行context →',
        'timer register → async_context_id → resume execution ID → fire/finish。',
        '公开handle按global区分，异步ID按process/session区分；无指针充当跨运行身份。',
        'finish只表示handler调用返回，未定义全局微任务检查点结束。', '',
        '## 实际结果', '',
        '| 检查 | 结果 |', '|---|---|',
        '| off及默认核心采集 | 生命周期记录0条，页面输出一致 |',
        '| 开启核心 / 核心+jscall | 各5注册、1取消、4 fire、4 finish，逐项唯一关联 |',
        '| frame/interval/string/retirement | 6注册、7次执行、1自取消、1 clear_all，全部闭合 |',
        '| 两个frame的handle=1 | WindowID/nativeId区分，互不混淆 |',
        '| cap=3 | 3条生命周期、1条显式gap，完整性校验按预期报错 |',
        '| gate关闭后开启 | 只记录session 1的新timer，不伪造关闭期注册 |',
        '| 已有异步链启用新开关 | 15个marker一致，3注册、2取消、4次执行闭合 |',
        '| 新构建默认串行/三进程并发回归 | off/core/calls各一轮通过，关系重新验证 |', '',
        '旧模式将未执行的timeout声明延后；新开关主动记录注册，因此取消的timeout',
        '也有schedule。已有串行样例set_timeout声明从1变2，这是覆盖扩大，不是重复',
        '声明。默认模式仍由原校验器验证，启用模式另核对取消生命周期。', '',
        '## 开关、预算与覆盖边界', '', '```powershell',
        "$env:MOZ_DOM_TRACE = '1'", "$env:MOZ_DOM_TRACE_TIMERS = '1'",
        "$env:MOZ_DOM_TRACE_TIMER_LIMIT = '16384'", '```', '',
        '运行器会清理继承的MOZ_DOM环境并显式传入配置，上述变量用于手动启动浏览器。',
        '事件上限每进程默认16384，可设1..1000000；非法值回默认。第一次超限输出',
        'timer_trace_gap，随后停止这一类记录，gate重开不重置预算。原writer丢弃统计',
        '继续独立检查。其余采集通道仍按各自预算工作。', '',
        '当前仅Window timeout/interval；Worker timer、idle/abort内部任务、门控关闭',
        '期间生命周期及全局检查点均未覆盖。delay_ms为register请求值，其他阶段为0，',
        '并非实际到期时间。未记录的旧capture不能由这次新构建补写历史事件。', '',
        '## 实测成本', '',
        '同一新构建三轮随机模式顺序，每轮每模式3个样本，共27个页内计时。每样本',
        '注册/取消2000个timer，预热200个，每进程共6200次。每份启用捕获实际包含',
        '6200 register和6200 cancel，未超限、writer无丢失。测量期间未并行构建或测试。', '',
        '| 模式 | 页内样本中位数 ms |', '|---|---:|']
    for mode, value in cost['page_medians_ms'].items(): lines.append(f'| {mode} | {value} |')
    lines += ['', f'按轮配对timers/core中位比{increment:.4f}，即本样例新增成本约{(increment-1)*100:.1f}%；',
        f'core/off中位比{core_ratio:.2f}。不能把不同分母的比值当作同一成本。',
        'CSV保留27个原样本，报告保留每轮比值。样本短且存在时间量化，背景负载未完全',
        '隔离；这不是回调执行/全网页成本，也不是上游无插桩对照。零开销目标未成立。', '',
        '## 测试和复现', '', '```powershell',
        'Set-Location D:\\BaiduNetdiskDownload\\ivv8\\ivv8\\ruyijs',
        'python -B -m tools.trace_audit.timer_identity_probe --output artifacts/timer-new',
        'python -B -m tools.trace_audit.timer_identity_cost --output artifacts/timer-cost-new',
        'python -B -m unittest discover -s tests -p test_timer_lifecycle.py -v', '```', '',
        f"12项新负例与既有离线测试合计{tests['tests']}项通过。实际Firefox构建成功，",
        '构建报告8条第三方警告。ruyijs二进制未变，无新增页面API或Proxy/wrapper。',
        '原始trace、before-source、实现差异、编译、回归、成本和源码hash保存在',
        'artifacts/timer-identity-20261024/validation.json。', '',
        'xul SHA256：`'+xul+'`。', '',
        '下一步是让ruyijs既有调度owner消费可映射的任务身份并检查就绪状态；本轮',
        '解决了新的Window timer捕获关联，尚未实现按记录选择任务或原网页业务成功。', '']
    (folder / 'TIMER_IDENTITY.md').write_text('\n'.join(lines), 'utf-8')
    firefox_sources = ['dom/base/nsGlobalWindowInner.cpp', 'dom/base/TimeoutManager.cpp', 'dom/bindings/moz.build',
        'dom/bindings/domtrace/TimerTraceLog.h', 'dom/bindings/domtrace/TimerTraceLog.cpp',
        'dom/bindings/domtrace/AsyncTraceLog.cpp', 'dom/bindings/domtrace/AsyncTraceCore.h']
    diff = []
    for name in firefox_sources:
        if 'TimerTrace' not in name and name not in firefox_sources[:3]: continue
        before = folder / 'before-source' / name
        diff.extend(difflib.unified_diff(before.read_text('utf-8').splitlines(True) if before.exists() else [],
                    (FIREFOX / name).read_text('utf-8').splitlines(True), fromfile='before/' + name, tofile='after/' + name))
    (folder / 'implementation.diff').write_text(''.join(diff), 'utf-8')
    sources = ['tools/trace_audit/' + name for name in ('timer_lifecycle.py', 'timer_identity_fixture.py',
        'timer_identity_probe.py', 'timer_identity_cost.py', 'timer_identity_report.py')]
    sources += ['tests/test_timer_lifecycle.py']
    reports = ['probe/result.json', 'cost/result.json', 'enabled-async/result.json', 'build.log', 'build-result.json',
        'regressions.json', 'async-regression/result.json', 'async-reverified.json', 'concurrent-regression/result.json',
        'concurrent-reverified.json', 'offline-tests-result.json', 'offline-tests.log', 'implementation.diff',
        'TIMER_IDENTITY.md', 'measurements.csv', 'before-source.json']
    raw = [p for p in folder.rglob('*') if p.is_file() and ('domtrace' in p.parts or 'jscall' in p.parts or p.name == 'user.js')]
    manifest = {'schema': 'local.timer-identity-report.v1', 'tests': tests, 'xul_sha256': xul,
        'runtime': {'shell_sha256': digest(ROOT / 'dist/js.exe'), 'client_sha256': digest(ROOT / 'dist/ruyijs_client.dll')},
        'sources': {name: digest(ROOT / name) for name in sources},
        'firefox_sources': {name: digest(FIREFOX / name) for name in firefox_sources},
        'reports': {name: digest(folder / name) for name in reports},
        'raw_evidence_files': [{'path': str(p.relative_to(folder)), 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in raw],
        'paired_timer_vs_core_median': increment, 'full_goal_complete': False}
    (folder / 'validation.json').write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    print(json.dumps({'published': True, 'tests': tests['tests'], 'raw_files': len(raw), 'xul_sha256': xul}))


if __name__ == '__main__': main()
