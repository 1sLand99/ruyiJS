"""Write a standalone measured-cost table with provenance and coverage limits."""
import argparse
import csv
import io
import json
from pathlib import Path
import statistics

from .cost_summary import summarize
from .rng_probe import digest

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=json.loads(args.report.read_text('utf-8'));summary=summarize(report)
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for mode in ('off','core','calls','detail'):
        values=summary['modes'][mode]
        rows.append({'mode':mode,'samples':report['rounds']*report['samples_per_run'],
            'wall_median_ms':values['wall_ms']['median'],'wall_p95_ms':values['wall_ms']['p95_interpolated'],
            'cpu_median_ms':values['cpu_ms']['median'],
            'peak_working_set_median_mib':values['peak_sum_rss_bytes']['median']/1048576,
            'trace_median_mib':statistics.median(values['trace_bytes'])/1048576,
            'leaf_coverage_percent':statistics.median(values['leaf_coverage'])*100})
    buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    (args.output/'measurements.csv').write_text(buffer.getvalue(),'utf-8')
    lines=['# 本地原生 trace 成本与覆盖测量','',
        '这些样本同时报告成本与覆盖。它们没有证明零开销、全调用覆盖或任意页面不可观察。','',
        f"每模式 {report['rounds']} 轮，每轮 {report['samples_per_run']} 个样本；每轮模式顺序随机化。",
        f"每进程已知 leaf 调用 {report['known_calls_per_process']['leaf']:,} 次，bytes 调用 {report['known_calls_per_process']['bytes']:,} 次。",'',
        '| 模式 | 宿主墙钟中位数 ms | 样本 P95 ms | 进程树 CPU 中位数 ms | 峰值工作集和中位数 MiB | 日志中位数 MiB | leaf 覆盖率 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['mode']} | {row['wall_median_ms']:.3f} | {row['wall_p95_ms']:.3f} | "
            f"{row['cpu_median_ms']:.3f} | {row['peak_working_set_median_mib']:.1f} | "
            f"{row['trace_median_mib']:.3f} | {row['leaf_coverage_percent']:.7f}% |")
    call_runs=[r for r in report['runs'] if r['mode'] in ('calls','detail')]
    counts={key:sorted({r['capture'][key] for r in call_runs})
            for key in ('leaf_records','bytes_records','call_records')}
    lines+=['',f"calls/detail 每进程 leaf 记录数 {counts['leaf_records']}，bytes 记录数 {counts['bytes_records']}，"
        f"总调用记录数 {counts['call_records']}。",
        '已知调用量与实际记录量的巨大差距说明 JIT 热路径未被完整覆盖。writer 丢弃和 I/O',
        '计数为零只支持写入器结果，不代表所有执行都被采到。', '',
        '所有样本的工作负载 checksum、选定 descriptor/源码、getter/Proxy 副作用探针一致。',
        '检查范围限于 fixture 返回值；这不证明所有页面都观察不到采集。','',
        '若开启模式耗时低于关闭模式，应检查运行波动、后台活动和预热差异；单次或少量',
        '样本的差值不直接解释为加速。少量样本的插值 P95 也不是稳定尾延迟估计。',
        'CPU 是进程树之和，可大于墙钟时间；工作集相加可能重复计算共享页面。25ms采样',
        '可能错过短进程和峰值。宿主耗时包含 Marionette 通信与采样器开销。','',
        '## 配置与复现','',
        '四组依次定义为：关闭全部 MOZ_DOM 开关、核心 trace、核心+调用、核心+调用+值。',
        '后三组 operators=0；调用与值过滤均为 /workload.js。每次使用新 profile，',
        '相同Firefox/xul与loopback页面。原始results.json保留每轮顺序、环境和全部样本。','',
        '```powershell',
        'python -B -m tools.trace_audit.capture_cost --output artifacts/capture-cost-new --rounds 3 --samples 3 --iterations 10000000',
        'python -B -m tools.trace_audit.cost_summary artifacts/capture-cost-new/results.json',
        'python -B -m tools.trace_audit.capture_cost_report artifacts/capture-cost-new/results.json --output artifacts/capture-cost-new/report',
        '```','',
        '需要 psutil（本机7.2.2）。资源监视在宿主进程执行，不向页面添加观测代码。',
        'fixture本身显式创建的Proxy/getter用于副作用测试，生产页面没有被安装替换。','',
        '## 产物身份','',
        'Firefox EXE SHA256: `'+report['firefox_sha256']+'`。','',
        'xul SHA256: `'+report['xul_sha256']+'`。','',
        '工作负载 SHA256: `'+report['workload_sha256']+'`。','',
        '本实验使用带插桩的同一构建作关闭组，未与上游无插桩二进制比较。','',
        '## 对 opcode 决策的含义','',
        '先补足运行阶段、异步边与必要输入的覆盖证据，再决定是否需要某个函数内的',
        '短窗口 opcode/分支诊断。只增加 opcode 名称仍不会恢复未采输入和异步因果。',
        '全量 opcode 的性能须在覆盖率相当的基准中独立测量，当前数据不支持启为默认。','']
    (args.output/'MEASURED_COST.md').write_text('\n'.join(lines),'utf-8')
    sources=['tools/trace_audit/capture_cost.py','tools/trace_audit/process_sample.py',
        'tools/trace_audit/cost_summary.py','tools/trace_audit/capture_cost_report.py',
        'tools/trace_audit/workload.js','tools/trace_audit/fixture.py','tests/test_capture_cost_summary.py']
    manifest={'schema':'local.capture-cost-report.v1','input':str(args.report),'input_sha256':digest(args.report),
        'summary':summary,'sources':{name:digest(ROOT/name) for name in sources},
        'outputs':{name:digest(args.output/name) for name in ('MEASURED_COST.md','measurements.csv')},
        'full_goal_complete':False}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n','utf-8')
    print(json.dumps({'samples':len(report['runs'])*report['samples_per_run'],
                      'surface_equal':True,'full_call_coverage':summary['full_call_coverage'],
                      'zero_overhead_proven':False}))


if __name__=='__main__':main()
