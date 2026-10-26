"""Publish native deferred-edge repair evidence and bounded local validation."""
import argparse
import difflib
import json
from pathlib import Path

from .rng_probe import digest
from .cost_summary import summarize
from .verify_object_snapshots import verify

ROOT=Path(__file__).resolve().parents[2]
FIREFOX=Path('D:/firefox/src/firefox')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'artifacts/async-proof-20261024')
    args=parser.parse_args();folder=args.folder.resolve();load=lambda p:json.loads(p.read_text('utf-8'))
    after=load(folder/'final-after/result.json');proof=load(folder/'final-evidence.json')
    before=load(folder/'before-evidence.json');edges=load(folder/'final-edge-cases/result.json')
    tests=load(folder/'all-tests-final-result.json');runtime=load(folder/'runtime-parity/result.json')
    if not proof['all_contexts_resolved'] or before['all_contexts_resolved']:
        raise ValueError('expected missing-before/resolved-after evidence')
    if not tests['passed'] or tests['returncode'] or not edges['verified'] or not runtime['passed']:
        raise ValueError('validation prerequisites missing')
    if proof['input_sha256']!=digest(folder/'final-after/result.json'):raise ValueError('proof/report identity differs')
    snapshot=load(folder/'final-object-regression/result.json');snapshot_summary=verify(snapshot)
    interval=load(folder/'final-interval-regression/result.json')
    if interval['missing_schedule'] or interval['duplicate_schedule_ids']:raise ValueError('interval regression')
    cost=load(folder/'final-cost/results.json');cost_summary=summarize(cost)
    xul=digest(FIREFOX/'obj-jscall-check/dist/bin/xul.dll')
    if any(item['xul_sha256']!=xul for item in (after,edges,snapshot,interval,cost)):
        raise ValueError('evidence spans different browser builds')
    if digest(ROOT/'dist/js.exe')!=runtime['shell_sha256'] or digest(ROOT/'dist/ruyijs_client.dll')!=runtime['client_sha256']:
        raise ValueError('runtime changed after parity test')
    for case in proof['cases']:
        if case['proof']['gaps'] or len(case['proof']['markers'])!=15:raise ValueError('local evidence incomplete')
        for source in case['sources']:
            if digest(Path(source['path']))!=source['sha256']:raise ValueError('source trace changed')
    implementation=list(load(folder/'source-before/manifest.json'))
    patch=[]
    for name in implementation:
        a=(folder/'source-before'/name).read_text('utf-8').splitlines(keepends=True)
        b=(FIREFOX/name).read_text('utf-8').splitlines(keepends=True)
        patch.extend(difflib.unified_diff(a,b,fromfile='before/'+name,tofile='after/'+name))
    (folder/'implementation.diff').write_text(''.join(patch),'utf-8')
    lines=['# 本地异步因果链：延迟声明漏写的修复与验证','',
        '本轮修复Firefox原生日志的关联缺口：普通DOM观察现在携带执行上下文身份，',
        '并使待写出的schedule/resume声明在被引用前进入现有writer。测试仅访问loopback。',
        '完整历史网页业务闭环未完成，当前证据不提供普遍不可观察或零开销结论。','',
        '## 修改前后','',
        '| 每份主探针捕获 | 修改前 | 修改后 |','|---|---:|---:|',
        '| 页面marker | 15 | 15 |','| 有声明的marker上下文 | 0 | 15 |',
        '| async_schedule | 1（interval） | 7 |','| async_resume | 3（interval） | 9 |',
        '| 唯一message send/receive配对 | 6 | 6 |','',
        '修改前页面行为正常，但microtask、Promise与一次性timeout没有明确调度边，',
        '消息可引用未声明执行上下文。真实脚本启动仍复现，不只是自动化调用根缺失。',
        '原因是异步声明有意延迟到观察时写出，而普通DOM日志没有通知该机制，自己也',
        '没有execution_context_id。旧interval修复单独提前写声明，因此它仍能连起来。','',
        '## 实现','',
        'AsyncTraceLog新增一个out-of-line调用转发到已有deferred-edge flush，避免头文件',
        '循环。DOM get/set/call在原gate与过滤后调用，记录execution_context_id、',
        'async_context_id、trace_session。MessageTraceCapture在现有gate内通知同一owner，',
        '使仅发送消息的Promise也有声明。原函数、回调、队列、JIT策略及JS接口没有更换。','',
        'trace_session取实际已接纳的gate会话，即使execution_context_id为0也不回退为',
        '默认会话；gate重开后的无脚本上下文记录有独立检查。','',
        '修复只覆盖已有观测路径；不把被取消timer或无观察callback强行记为已执行。',
        'schedule记录时间是延迟写入时间，不是enqueue timestamp。async_resume没有end',
        '记录，因此分析按显式ID关联，不依据最近一行或墙钟推测上下文。','',
        '## 已验证路径','',
        '两轮off/core/calls共六次页面运行，15个marker次序相同。四份启用捕获各有',
        '2条queue_microtask、3条promise_reaction、1条set_timeout、1条set_interval声明；',
        'interval三次恢复各自有唯一execution ID且共用schedule ID。消息涵盖self window、',
        'MessageChannel、iframe往返、Worker往返，共6次唯一配对。所有声明引用都能解析。','',
        'calls组还验证每个origin_call_id指向真实binary中的record函数。同步自定义事件',
        '沿外层timeout的上下文，未虚构独立异步节点。通用event listener日志有采样且',
        '该自定义事件不在全量输入事件范围，本次不要求其存在。首次使用的无效环境变量',
        'MOZ_DOM_TRACE_EVENTS已移除；它从未作为完整事件证据。','',
        '边界组get/set/static/nested/gate全部通过。gate关闭前观察未写出，重开后新脚本',
        '建立上下文并可关联。原interval probe无missing schedule，七组对象快照继续',
        '通过，getter/Proxy/toJSON副作用计数为0。11项离线负例检查ID歧义、丢失引用、',
        f"错误cause、传输字段改变及writer丢弃，完整{tests['tests']}项回归通过。",'',
        'ruyijs Python和C DLL执行相同本地fixture得到相同15项顺序；这叫行为一致性，',
        '没有消费Firefox task计划，因此不称为从该异步trace确定性回放。','',
        '## 成本与局限','',
        '新xul复跑四模式三轮36样本，探针表面和checksum一致。宿主墙钟中位数：']
    for mode in ('off','core','calls','detail'):
        lines.append(f"- {mode}: {cost_summary['modes'][mode]['wall_ms']['median']:.3f} ms。")
    lines+=['','部分off样本波动较大，历史构建未交替配对，不作精确前后增量推断。新字段及',
        '必要边写出都有非零成本。调用覆盖仍为3020万leaf中的26次，因此该基准不证明',
        '完整执行采集低开销。消息/DOM层实验也不解决原网页的输入和全局任务顺序。','',
        '## 复现','',
        '```powershell',
        'python -B -m tools.trace_audit.async_probe --output artifacts/async-new --rounds 2',
        'python -B -m tools.trace_audit.verify_async_probe artifacts/async-new/result.json --output artifacts/async-new/evidence.json --require-contexts',
        'python -B -m tools.trace_audit.async_edges_probe --output artifacts/async-edges-new',
        'python -B -m tools.trace_audit.async_runtime_probe --output artifacts/async-runtime-new',
        '```','',
        '页面marker是本地fixture本身，不是注入第三方页面的wrapper。run目录保存精确',
        '环境、源码hash、xul身份和每行证据。实现diff、失败捕获和最终结果分别保留。','',
        'xul SHA256：`'+xul+'`。构建成功，0编译警告。ruyijs二进制未变。','']
    (folder/'ASYNC_CAUSAL_PROOF.md').write_text('\n'.join(lines),'utf-8')
    sources=['tools/trace_audit/'+name for name in ('async_workload.js','async_fixture.py','async_probe.py',
        'async_evidence.py','verify_async_probe.py','async_edges_probe.py','async_runtime_probe.py','async_report.py')]
    sources+=['tests/test_async_evidence.py']
    reports=['final-after/result.json','script-start-before/result.json','before-evidence.json','final-evidence.json',
        'final-edge-cases/result.json','runtime-parity/result.json','final-interval-regression/result.json',
        'final-object-regression/result.json','final-cost/results.json','all-tests-final-result.json','all-tests-final.log',
        'build-final.log','implementation.diff','ASYNC_CAUSAL_PROOF.md']
    manifest={'schema':'local.async-proof-report.v1','tests':tests,'xul_sha256':xul,
        'runtime':{key:runtime[key] for key in ('shell_sha256','client_sha256')},
        'local_contexts_resolved':True,'full_goal_complete':False,
        'sources':{name:digest(ROOT/name) for name in sources},
        'firefox_sources':{name:digest(FIREFOX/name) for name in implementation},
        'reports':{name:digest(folder/name) for name in reports},'snapshot_validation':snapshot_summary}
    (folder/'validation.json').write_text(json.dumps(manifest,indent=2)+'\n','utf-8')
    print(json.dumps({'tests':tests['tests'],'native_trace_cases':4,'markers_each':15,
        'schedule_edges_each':9,'message_edges_each':6,'full_goal_complete':False}))


if __name__=='__main__':main()
