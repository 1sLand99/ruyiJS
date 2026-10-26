"""Publish the local call/value proof and source replay with verified artifacts."""
import argparse
import json
from pathlib import Path

from .rng_probe import digest

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'artifacts/tier-integrity-20261024')
    args=parser.parse_args();folder=args.folder.resolve()
    load=lambda p:json.loads(p.read_text('utf-8'))
    proof=load(folder/'verified-types/result.json');replay=load(folder/'native-replay-types/result.json')
    tests=load(folder/'all-tests-final-result.json')
    if not proof.get('verified') or not replay.get('verified') or not tests['passed'] or tests['returncode']:
        raise ValueError('validation prerequisites missing')
    if replay['proof_sha256']!=digest(folder/'verified-types/result.json'):
        raise ValueError('replay used a different proof')
    for name,expected in proof['sources'].items():
        if digest(Path(__file__).with_name(name))!=expected:raise ValueError('proof source changed')
    for name,key in (('js.exe','shell_sha256'),('ruyijs_client.dll','client_sha256')):
        if digest(ROOT/'dist'/name)!=replay[key]:raise ValueError('runtime binary changed')
    prior=load(ROOT/'artifacts/tier-cost-20261024/validation.json')
    if replay['shell_sha256']!=prior['stable_runtime']['js.exe']:
        raise ValueError('runtime differs from stable experiment baseline')
    for row in proof['runs']:
        for name,expected in row['sources'].items():
            if digest(ROOT/'artifacts/tier-cost-20261024'/name)!=expected:
                raise ValueError('original evidence file changed')
    selected=[row for row in proof['runs'] if row['tier']=='interpreter']
    normal=[row for row in proof['runs'] if row['tier']=='normal']
    if len(selected)!=3 or len(normal)!=3 or len(replay['cases'])!=6:
        raise ValueError('missing proof or replay case')
    by_round={row['round']:row['recovered_runs'] for row in selected}
    for case in replay['cases']:
        expected=by_round[case['round']]
        if len(case['outputs'])!=len(expected):raise ValueError('missing replay input')
        for output,source in zip(case['outputs'],expected):
            if output['arguments']!=source['arguments'] or output['checksum']!=source['checksum']:
                raise ValueError('replay differs from proven inputs/results')
    lines=['# 本地静态 trace：调用关系、数值证据与双接口重放','',
        '本报告复用已保存的执行层实验，不启动目标站点、不修改浏览器API或运行时。',
        '结论限定于tier_workload.js这个已知同步计算样例。完整网页异步和业务闭环仍未完成。','',
        '## 核验结果','',
        f"三轮正常JIT与三轮解释执行detail日志共核验{proof['total_leaf_returns']:,}次leaf返回，",
        f"全部数值函数返回合计{proof['total_numeric_returns']:,}次。正常组只验证存在的稀疏记录；",
        '解释执行组进一步验证完整迭代输入次序、wrapper参数转换、子调用数量和每轮checksum。','',
        '| 每份捕获 | normal/detail | interpreter/detail |',
        '|---|---:|---:|',
        f"| 完整返回调用 | {normal[0]['completed_calls']:,} | {selected[0]['completed_calls']:,} |",
        f"| leaf数值返回 | {normal[0]['leaf_returns']:,} | {selected[0]['leaf_returns']:,} |",
        f"| bytes数值返回 | {normal[0]['byte_returns']:,} | {selected[0]['byte_returns']:,} |",
        f"| wrapper数值返回 | {normal[0]['wrapper_returns']:,} | {selected[0]['wrapper_returns']:,} |",
        f"| caller JIT gap标记 | {normal[0]['caller_jit_gaps']:,} | {selected[0]['caller_jit_gaps']:,} |",
        f"| 由完整返回序列恢复的run checksum | {normal[0]['run_checksums']} | {selected[0]['run_checksums']} |",'',
        '输入/返回值检查覆盖全部已记录leaf和wrapper整数值，bytes参数要求真实1024字节',
        '零缓冲且返回1024。run返回仍只是Object类名；其字段不视为已捕获。最终checksum',
        '从完整标量返回序列重新推导，再与当时直接读取的页面结果核对。','',
        '## 调用边语义','',
        '已知源码关系如下；其中run可直接调用leaf，也可经两个wrapper调用：','',
        '```mermaid','flowchart LR','  run --> measuredLeaf','  run --> shiftedOne',
        '  run --> shiftedTwo','  shiftedOne --> measuredLeaf','  shiftedTwo --> measuredLeaf',
        '  run --> measuredBytes','```','',
        '完整解释执行组每个父ID存在、同线程且早于child分配；parent的leave晚于child，',
        'depth相差1。JSCV的this/arg/return嵌套与JSCT逐项对应，返回顺序必须和binary',
        'leave顺序相同。重复ID、缺返回、参数slot重复/缺失都拒绝。','',
        '默认JIT组每份有30个caller-gap标记。即使观测边恰好符合这份源码的拓扑，也',
        '没有足够记录恢复其全部循环。parentCallId应解释为最近被记录祖先；缺少gap标记',
        '本身同样不是任意程序的直接调用证明。完整组的结论额外依赖已知源码与每次输入',
        '次序验证。只按记录数量相等会漏掉交换顺序或用重复正确值替代丢失值的错误。','',
        '## 从静态记录到ruyijs结果','',
        '每份解释执行记录恢复四组输入：一次(10000,1000)，三次(250000,1000)。',
        '独立整数模型严格执行32位截断和无符号右移，推导checksum；运行参数只从JSCV',
        'run参数提取。三个捕获分别进入新Context，经Python和实际C DLL各执行一次。',
        '共6个上下文、24次run，全部与trace推导结果相同。原始JS源码hash固定，资源',
        '通过现有catalog加载到本地URL，逻辑时钟仅供执行，未重放历史计时。','',
        '这里的“本地重放通过”是可核验的小样例结论，不是原网页的网络、消息、RNG、',
        'GC、渲染或异步调度已回放。默认JIT的稀疏输入没有被提升为完整重放证据。','',
        '## 测试与复现','',
        '14项格式/语义破坏测试覆盖：错误数值、整数/布尔混淆、正确值但错误输入次序、缺参数、重复slot、',
        '重复call、跨线程/缺parent、leave先后错误、gap冒充完整、截断、尾随残片和',
        f"错误checksum。完整回归{tests['tests']}项通过。生产runtime未变。",'',
        '```powershell',
        'python -B -m tools.trace_audit.tier_integrity artifacts/tier-cost-20261024/final/results.json --output artifacts/integrity-new',
        'python -B -m tools.trace_audit.local_trace_replay artifacts/integrity-new/result.json --output artifacts/local-replay-new',
        'python -B -m unittest discover -s tests -p test_tier_integrity.py -v',
        '```','',
        '校验器先核对先前manifest内原文件SHA256。JSCT文件以只读mmap访问；JSCV逐条读取，',
        '只保存活跃调用栈，避免将每个对象内容复制到内存。完整函数计算结果按输入缓存，',
        '每条实际记录仍逐条校验。第一版工具因Windows路径分隔符不一致停止，修正后',
        '输出到新目录；早期结果保留，最终使用verified-types及native-replay-types。','',
        '## 证据身份','',
        'shell SHA256：`'+replay['shell_sha256']+'`。','',
        'C DLL SHA256：`'+replay['client_sha256']+'`。','',
        '工作负载 SHA256：`'+proof['workload_sha256']+'`。','',
        '源码/输入/报告hash以及全部核验计数见validation.json。没有新浏览器采集，因此',
        '本轮离线运行时间不是采集开销数据；开销结论仍见上一份TIER_COST报告。','']
    (folder/'LOCAL_TRACE_PROOF.md').write_text('\n'.join(lines),'utf-8')
    sources=['tools/trace_audit/'+name for name in ('local_call_index.py','tier_oracle.py',
        'tier_value_proof.py','tier_integrity.py','local_trace_replay.py','tier_integrity_report.py')]
    sources+=['tests/test_tier_integrity.py','tools/trace_audit/tier_workload.js']
    outputs=['LOCAL_TRACE_PROOF.md','verified-types/result.json','native-replay-types/result.json',
             'all-tests-final-result.json','all-tests-final.log']
    manifest={'schema':'local.trace-proof-report.v1','tests':tests,'full_goal_complete':False,
        'leaf_returns_verified':proof['total_leaf_returns'],'numeric_returns_verified':proof['total_numeric_returns'],
        'native_replay_runs':24,'sources':{name:digest(ROOT/name) for name in sources},
        'reports':{name:digest(folder/name) for name in outputs}}
    (folder/'validation.json').write_text(json.dumps(manifest,indent=2)+'\n','utf-8')
    print(json.dumps({k:manifest[k] for k in ('tests','leaf_returns_verified','numeric_returns_verified','native_replay_runs','full_goal_complete')}))


if __name__=='__main__':main()
