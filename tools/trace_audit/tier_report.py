"""Generate a reproducible report for tier coverage/cost and the opcode decision."""
import argparse
import csv
import io
import json
from pathlib import Path
import statistics

from .rng_probe import digest
from .tier_summary import summarize
from .tier_plot import render
from .tier_capture import collect

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plot-deps',type=Path)
    parser.add_argument('--verify-binaries',action='store_true')
    args=parser.parse_args();report=json.loads(args.input.read_text('utf-8'))
    if digest(ROOT/'tools/trace_audit/tier_workload.js')!=report['workload_sha256']:
        raise ValueError('current fixture source differs from this experiment')
    if args.verify_binaries:
        for row in report['runs']:
            folder=args.input.parent/f"{row['round']}-{row['tier']}-{row['mode']}"
            if collect(folder)!=row['capture']:raise ValueError('capture changed since measurement')
    summary=summarize(report);args.output.mkdir(parents=True,exist_ok=True)
    plot_version=render(report,summary,args.output,args.plot_deps)
    rows=[]
    for tier in ('normal','interpreter'):
        for mode in ('off','calls','detail'):
            cell=summary['cells'][tier+'/'+mode]
            rows.append({'tier':tier,'mode':mode,'page_median_ms':cell['page_median_ms'],
                'host_median_ms':cell['host_median_ms'],
                'leaf_coverage_percent':statistics.median(cell['coverage']['measuredLeaf'])*100,
                'bytes_coverage_percent':statistics.median(cell['coverage']['measuredBytes'])*100,
                'trace_median_mib':statistics.median(cell['trace_bytes'])/1048576,
                'call_records':statistics.median(cell['call_records'])})
    buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    (args.output/'TIER_COST.csv').write_text(buffer.getvalue(),'utf-8')
    ratio=lambda name:summary['ratios'][name]['median']
    text=['# 执行层、调用覆盖与采集成本：opcode 决策实验','',
        '结论：默认JIT配置的热调用覆盖稀疏；强制解释执行可以补齐本样例调用，但执行层',
        '变化本身成本显著。当前结果支持把高覆盖诊断作为独立模式，不支持为常规trace',
        '默认关闭JIT。本实验没有实现或测量opcode日志，因此不声称已经得出其准确成本。','',
        '![调用耗时、覆盖率和日志大小](TIER_COST.png)','',
        '## 方法','',
        f"{report['rounds']}轮随机顺序、每模式每轮{report['samples']}个样本，六个组合共{len(report['runs'])*report['samples']}个计时样本。",
        '每组使用全新Firefox进程/profile；正常模式保留Baseline Interpreter、Baseline JIT、',
        'Ion；诊断模式在启动前关闭三者。启动后从chrome上下文读取实际pref再加载loopback',
        '页面。脚本内容相同，checksum及选定descriptor/getter/Proxy探针逐项相等。','',
        '三种采集模式为关闭、独立jscall、独立jscall+detail；核心DOM日志关闭，过滤只匹配',
        '/tier-workload.js。原页面API没有被wrapper替换。Chrome上下文只用于读配置，',
        '工作负载执行在内容页面。实际产物身份和每组配置都在results.json。','',
        f"每次页面测量执行{report['iterations']:,}次leaf调用，每次leaf包含32次整数混合操作；",
        f"每次浏览器运行含预热共{report['known_calls']['measuredLeaf']:,}次leaf、{report['known_calls']['measuredBytes']:,}次bytes调用。",
        '解码器从实际二进制记录按函数与源码URL计数，核对writer终态记录数、I/O与丢弃',
        '计数、detail完整性。首次预实验页内耗时约1ms，保留但不混入正式统计。','',
        '## 结果','',
        '| 执行层 | 采集 | 页内中位数 ms | 宿主中位数 ms | leaf覆盖率 | bytes覆盖率 | 日志 MiB |',
        '|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        text.append(f"| {row['tier']} | {row['mode']} | {row['page_median_ms']:.1f} | {row['host_median_ms']:.1f} | "
            f"{row['leaf_coverage_percent']:.5f}% | {row['bytes_coverage_percent']:.3f}% | {row['trace_median_mib']:.4f} |")
    text+=['',f"按轮配对中位数，关闭执行层但不采集为正常不采集的{ratio('tier_without_trace'):.2f}倍；",
        f"在相同解释执行层内，calls为off的{ratio('interpreter_calls_vs_off'):.3f}倍，",
        f"detail为off的{ratio('interpreter_detail_vs_off'):.3f}倍。",
        f"解释执行+detail相对正常off为{ratio('interpreter_detail_vs_normal_off'):.2f}倍，",
        '这是执行策略和采集成本的组合，不应全部归为writer开销。每轮原始比值在摘要JSON中。','',
        '解释执行组两个已知函数的调用计数达到100%；正常组覆盖率低。该100%仅覆盖',
        '本fixture已知函数和调用次数，不证明浏览器所有tier、事件、宿主API或异步路径',
        '完整。没有writer丢弃也不等于执行覆盖完整。','',
        '## 限制与论文写法','',
        '重复轮数有限，后台负载未完全隔离；正常模式的几十毫秒样本受定时器量化与噪声影响。',
        '图保留全部原样本，黑线是中位数，不画未经验证的置信区间。预热和测量的全部',
        '日志纳入字节统计。宿主耗时包含Marionette；页内耗时由performance.now测量。',
        '该实验不采CPU/内存，相关字段见上一份CAPTURE_COST报告，两个不同工作负载',
        '的绝对时间不混合。off仍是带插桩的同一构建，不是上游无插桩构建。','',
        '建议论文写成：“在本地已知调用量实验中，关闭JIT诊断可达到所测函数的完整',
        '覆盖，同时产生显著运行成本；默认JIT下当前VM采集点覆盖稀疏。”避免写成',
        '“全量opcode低开销”“关闭JIT对页面无影响”或“记录未丢失即执行完整”。','',
        '## 下一步选择','',
        '1. 常规采集先定义每类记录覆盖契约，保留caller-gap与预算标记。',
        '2. 对所需输入及异步因果采用有限目标边界，分别验证实际覆盖与行为。',
        '3. 只有内部首分歧仍未解释时，启用受预算限制的opcode/分支/值短窗口，并将',
        '   deopt、tier变化、覆盖、CPU/内存及输出字节独立测量。',
        '4. 通用工具在独立本地样例验证；本报告没有推进第三方验证码响应仿真。','',
        '## 复现','',
        '```powershell',
        'python -B -m tools.trace_audit.tier_probe --output artifacts/tier-new --rounds 3 --samples 3 --iterations 250000 --warmup 10000 --byte-calls 1000',
        'python -B -m tools.trace_audit.tier_summary artifacts/tier-new/results.json --output artifacts/tier-new/summary.json',
        'python -m pip install --target artifacts/tier-plot-deps matplotlib',
        'python -B -m tools.trace_audit.tier_report artifacts/tier-new/results.json --output artifacts/tier-new/report --plot-deps artifacts/tier-plot-deps --verify-binaries',
        '```','',
        '新文件夹保留每次结果，运行器退出会关闭自己启动的浏览器，不操作用户浏览器。',
        '提供PNG、SVG、PDF和CSV；图中文字英文以便跨机器稳定导出。','',
        '## 身份','',
        'Firefox：`'+report['firefox_sha256']+'`。','',
        'xul：`'+report['xul_sha256']+'`。','',
        '工作负载：`'+report['workload_sha256']+'`。','',
        'Searchfox查询确认三个pref启动时读取；本机searchfox-cli 0.18.0，提示新版0.20.5。',
        '实际启动配置读回与调用计数提供本地证据，不依赖在线代码版本完全等同于构建。','']
    selection=args.input.parent.parent/'measurement-selection.json'
    if selection.exists():
        text+=['## 样本选择','',
            'pilot的原始工作负载耗时约1ms；paired测量与绘图库安装时间有重叠。两批结果',
            '保留为先导数据，均未纳入本报告。最终final批次在依赖安装完成后重跑，期间',
            '未并行构建、运行测试或安装；用户原有应用未关闭，残余后台负载限制仍保留。','']
    (args.output/'TIER_COST.md').write_text('\n'.join(text),'utf-8')
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n','utf-8')
    sources=['tools/trace_audit/'+name for name in ('tier_workload.js','tier_fixture.py','tier_capture.py',
        'tier_probe.py','tier_summary.py','tier_plot.py','tier_report.py')]+['tests/test_tier_summary.py']
    outputs=['TIER_COST.'+suffix for suffix in ('md','csv','svg','pdf','png')]+['summary.json']
    manifest={'schema':'local.tier-report.v1','input_sha256':digest(args.input),'input':str(args.input),
        'matplotlib_version':plot_version,'raw_capture_reverified':args.verify_binaries,
        'sources':{name:digest(ROOT/name) for name in sources},
        'outputs':{name:digest(args.output/name) for name in outputs},'full_goal_complete':False}
    if selection.exists():manifest['measurement_selection_sha256']=digest(selection)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n','utf-8')
    print(json.dumps({'samples':len(report['runs'])*report['samples'],'fixture_calls_complete_in_interpreter':
        summary['fixture_calls_complete_in_interpreter'],'ratios':summary['ratios'],'full_goal_complete':False}))


if __name__=='__main__':main()
