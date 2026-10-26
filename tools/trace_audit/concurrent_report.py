"""Publish cross-process equal-payload message proof with partial-order limits."""
import argparse
from collections import defaultdict
import itertools
import json
from pathlib import Path

from .async_evidence import load_rows
from .concurrent_verify import prove
from .concurrent_fixture import SCRIPT_RESOURCES
from .message_graph import MessageGraph
from .rng_probe import digest

ROOT=Path(__file__).resolve().parents[2]
FIREFOX=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'artifacts/concurrent-proof-20261024')
    args=parser.parse_args();folder=args.folder.resolve()
    load=lambda path:json.loads(path.read_text('utf-8'))
    capture=load(folder/'capture/result.json');proof=load(folder/'final-proof.json')
    tests=load(folder/'all-tests-final-result.json')
    if not proof['verified'] or not tests['passed'] or tests['returncode']:
        raise ValueError('verification/test prerequisite missing')
    if proof['input_sha256']!=digest(folder/'capture/result.json'):raise ValueError('capture/proof identity differs')
    import hashlib
    if {name:hashlib.sha256(body).hexdigest() for name,body in SCRIPT_RESOURCES.items()}!=capture['script_hashes']:
        raise ValueError('current fixture differs from recorded source')
    if digest(FIREFOX/'xul.dll')!=capture['xul_sha256']:raise ValueError('current browser differs from capture')
    prior=load(ROOT/'artifacts/async-proof-20261024/validation.json')
    if prior['xul_sha256']!=capture['xul_sha256']:raise ValueError('browser changed after async repair')
    for name,key in (('js.exe','shell_sha256'),('ruyijs_client.dll','client_sha256')):
        if digest(ROOT/'dist'/name)!=prior['runtime'][key]:raise ValueError('stable runtime changed')
    checks=[];seen_ids=set()
    for case in proof['cases']:
        page=next(r for r in capture['cases'] if r['round']==case['round'] and r['mode']==case['mode'])
        base=folder/'capture'/page['folder'];rows,_=load_rows(base)
        if prove(rows,page['page'],base,page['mode'])!=case['proof']:raise ValueError('proof not reproducible')
        for source in case['sources']:
            if digest(Path(source['path']))!=source['sha256']:raise ValueError('trace source changed')
        by_file=defaultdict(list)
        for row in rows:by_file[row['file']].append(row)
        graph=MessageGraph(rows)
        lineage={key:graph.incoming_for_send(key) for key in graph.messages}
        for permutation in itertools.permutations(by_file):
            permuted=MessageGraph([row for file in permutation for row in by_file[file]])
            if {key:permuted.incoming_for_send(key) for key in permuted.messages}!=lineage:
                raise ValueError('cross-file merge order affected causality')
        if seen_ids.intersection(graph.messages):raise ValueError('message IDs collided across captures')
        seen_ids.update(graph.messages)
        checks.append({'round':case['round'],'mode':case['mode'],'file_order_permutations':6,
                       'numeric_context_reuse':case['proof']['numeric_context_ids_reused_across_processes']})
    orders=[''.join(label.split(':')[2] for label in case['page']['order'] if label.startswith('parent:receive:'))
            for case in capture['cases']]
    lines=['# 并发跨进程消息：相同正文下的因果验证','',
        '本轮使用三个不同站点的loopback页面和各frame自己的Worker，验证ID是否足以',
        '重建并发往返。未修改浏览器/ruyijs二进制，没有访问第三方页面。完整历史网页',
        '业务闭环仍未完成。','',
        '## 实际路径','',
        '```mermaid','flowchart LR','  P[主页面进程] -->|ping| F1[iframe 1 进程]',
        '  P -->|ping| F2[iframe 2 进程]','  F1 -->|Promise → ping| W1[Worker 1]',
        '  F2 -->|Promise → ping| W2[Worker 2]','  W1 -->|Promise → pong| F1',
        '  W2 -->|Promise → pong| F2','  F1 -->|Promise → pong| P','  F2 -->|Promise → pong| P','```','',
        '三个不同.test站点由Firefox localDomains映射到同一127.0.0.1服务器，启动后',
        '读取fissionAutostart确认隔离开启。实际script_root证明三个不同内容进程；',
        '每个Worker留在所属frame进程中，故不把Worker消息也计成跨进程传输。','',
        '每个frame收到8次相同ping，Worker回相同pong，frame再回相同pong。消息不携带',
        '分支或请求序号。页面用event.source计数和标记结果，trace用独立message_id',
        '连接发送与接收。两份ready握手加16条四跳数据往返，共66条消息。','',
        '## 结果','',
        '| 每份enabled捕获 | 数量 |','|---|---:|','| 独立内容进程 | 3 |',
        '| Worker | 2 |','| 完整往返路径 | 16 |','| message send/receive唯一配对 | 66 |',
        '| 真正跨进程的消息 | 34 |','| 所属进程内Worker消息 | 32 |','| Promise schedule/resume配对 | 48 |',
        '| 页面/iframe marker | 68 |','',
        '两轮off/core/calls六次页面运行均各路收到8次回复；四份enabled捕获均通过完整',
        'ID证明。每份66条消息加起来264条，跨捕获message_id也没有碰撞。每份文件',
        '合并次序枚举6种排列，所有消息的来源链结果保持一致；检查未使用墙钟全排序。','',
        '## 逐跳证明规则','',
        '1. execution identity由process_instance_id/session/ID组成，进程内重复数字',
        '   在不同命名空间中保留独立身份；源消息token须属于实际发送进程。',
        '2. 同message_id只允许一个send和receive；sender nonce、session、source context、',
        '   async ID、序号及本fixture的global端点在传输两侧一致。',
        '3. 每次回复从source context沿唯一Promise resume→schedule→parent context',
        '   反查到输入message_receive，三条Promise边串成四跳往返。',
        '4. worker_created的owner_window_id/worker_id证明frame↔Worker端点；两个分支',
        '   不共享消息，最后回包必须落到同一分支、同序号的页面marker。',
        '5. 调用日志开启时，marker origin_call_id必须存在于同PID实际binary，并在',
        '   捕获的脚本栈中唯一匹配。跳过内层采集点后的外层匹配单独记为observed_ancestor。','',
        '各calls捕获的调用来源分类：','']
    for case in proof['cases']:
        if case['mode']=='calls':lines.append(f"- round {case['round']}: {case['proof']['marker_call_origin_kind']}。")
    lines+=['','这次真实例子表明origin_call_id也可能仅是外层已观察调用。即使该调用自身的',
        'caller-gap未设置，也不应把DOM到该ID的边强称为直接调用；需要参考记录契约',
        '及实际栈。不能要求全部ID都指向最内层record/mark，否则会把合法稀疏trace',
        '误判为错误；也不能忽略来源ID而只看数量。','',
        '## 偏序与验证边界','',
        f"六次页面接收交错共有{len(set(orders))}种不同序列（0/1仅标识frame分支）：",'']
    for case,order in zip(capture['cases'],orders):lines.append(f"- round {case['round']} / {case['mode']}: `{order}`。")
    lines+=['','每路FIFO都成立，跨路交错允许变化。显式因果边支持偏序，未推导唯一全局任务',
        '顺序；时间戳相同或先后都不替代ID。该样例不含取消/跨会话未完成任务、端口',
        '转移、广播或独立Worker进程，不对这些路径提出完成结论。',
        '没有把记录计划交给ruyijs调度，因此本轮是静态因果验证，不是异步确定性回放。','',
        '## 测试与复现','',
        '13项测试覆盖同值ID冲突、不同进程同数字ID、乱序/相同时间戳、重复/缺消息、',
        '更改端点、伪造source、错误会话、缺schedule、循环上下文和JSON落盘往返。',
        f"完整{tests['tests']}项回归通过。最终浏览器及运行时hash与上一轮一致。",'',
        '```powershell',
        'python -B -m tools.trace_audit.concurrent_probe --output artifacts/concurrent-new --rounds 2',
        'python -B -m tools.trace_audit.concurrent_verify artifacts/concurrent-new/result.json --output artifacts/concurrent-new/proof.json',
        'python -B -m unittest discover -s tests -p test_message_graph.py -v',
        '```','',
        '全部资源由本地HTTP服务提供；Fission配置只写入本次新profile。原始trace、',
        '每次页面结果、source hash、逐跳ID路径和测试结果都保留。初版过严的“全部来源',
        '必须是最内层函数”断言已由实际记录修正，最终报告保留其语义限制。报告初次',
        '重验还暴露元组和JSON数组的表示差异；输出统一为数组，并增加往返验证，',
        '随后原始捕获重验通过，未用宽松字段匹配掩盖ID或因果差异。','',
        'xul：`'+capture['xul_sha256']+'`。','']
    (folder/'CONCURRENT_MESSAGE_PROOF.md').write_text('\n'.join(lines),'utf-8')
    sources=['tools/trace_audit/'+name for name in ('concurrent_parent.js','concurrent_fixture.py',
        'concurrent_probe.py','message_graph.py','concurrent_verify.py','concurrent_report.py')]
    sources+=['tests/test_message_graph.py','tools/trace_audit/async_evidence.py']
    reports=['capture/result.json','final-proof.json','all-tests-final-result.json','all-tests-final.log','CONCURRENT_MESSAGE_PROOF.md']
    manifest={'schema':'local.concurrent-report.v1','tests':tests,'xul_sha256':capture['xul_sha256'],
        'file_order_checks':checks,'unique_message_ids_across_captures':len(seen_ids),
        'interleaving_variants':len(set(orders)),'full_goal_complete':False,
        'runtime':prior['runtime'],
        'sources':{name:digest(ROOT/name) for name in sources},'reports':{name:digest(folder/name) for name in reports}}
    raw=[]
    for case in capture['cases']:
        base=folder/'capture'/case['folder']
        files=list((base/'domtrace').glob('*.jsonl'))+list((base/'jscall').glob('*'))+[base/'profile/user.js']
        raw += [{'path':str(path.relative_to(folder)),'bytes':path.stat().st_size,'sha256':digest(path)}
                for path in files if path.is_file()]
    manifest['raw_evidence_files']=raw
    (folder/'validation.json').write_text(json.dumps(manifest,indent=2)+'\n','utf-8')
    print(json.dumps({'tests':tests['tests'],'message_pairs':len(seen_ids),'file_permutations':24,
        'interleaving_variants':len(set(orders)),'full_goal_complete':False}))


if __name__=='__main__':main()
