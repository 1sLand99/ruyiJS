"""Aggregate observed surface and behavior differences without claiming full parity."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/firefox_parity'))
from report import compare as compare_surface


def differences(left, right, path=''):
    if type(left) is not type(right):
        return [{'path':path, 'firefox':left, 'ruyijs':right}]
    if isinstance(left, dict):
        return [row for key in sorted(set(left) | set(right))
                for row in differences(left.get(key), right.get(key), path+'.'+key)]
    if isinstance(left, list):
        if len(left) != len(right):
            return [{'path':path+'.length', 'firefox':len(left), 'ruyijs':len(right)}]
        return [row for index, (a,b) in enumerate(zip(left,right))
                for row in differences(a,b,path+f'[{index}]')]
    return [] if left == right else [{'path':path, 'firefox':left, 'ruyijs':right}]


def owner(name):
    for pattern, value in [
        (r'Canvas|TextMetrics|ImageBitmap|Path2D', 'WEB_CANVAS'),
        (r'WebGL|WEBGL|GL_', 'WEB_GRAPHICS'), (r'^GPU', 'WEB_GPU'),
        (r'Audio|Oscillator|Biquad|Gain|Panner|WaveShaper|Analyser', 'WEB_AUDIO'),
        (r'^RTC', 'WEB_RTC'), (r'CSS|Style|MediaQuery', 'WEB_STYLING'),
        (r'FontFace', 'FONT_FACE'), (r'Performance', 'PERFORMANCE'),
        (r'Fetch|Request|Response|Headers|Stream|Blob|File$', 'RESOURCE_NETWORK'),
        (r'^IDB', 'INDEXED_DB'), (r'Storage|FileSystem', 'STORAGE'),
        (r'Worker', 'WORKER'), (r'^Crypto|Subtle', 'CRYPTO'),
        (r'Permission', 'PERMISSIONS'), (r'Media|Video|TextTrack', 'MEDIA_DEVICES'),
        (r'Event|Touch|Mouse|Pointer|Keyboard', 'INTERACTION'),
        (r'HTML|SVG|Document|Element|Node|Attr|Range|DOM', 'DOCUMENT_MODEL'),
        (r'Navigator|Screen|History|Window|Location', 'BROWSER_ENVIRONMENT'),
    ]:
        if re.search(pattern,name):
            return value
    return 'REQUIRES_OWNER_REVIEW'


def canonical(path):
    path = path.replace('chains.', 'interfaces.', 1) if path.startswith('chains.') else path
    path = path.replace('instances.window.', 'window.', 1)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    folder = args.directory.resolve()
    surface = json.loads((folder/'surface/differences.json').read_text('utf-8'))
    report = {'scope':'captured Window/iframe/Worker surfaces and finite local behavior probes',
              'full_environment_parity_proven':False,'business_closure_proven':False,
              'surface':{}, 'behavior':{},'worker_surface':{},'owner_counts':{},'capture_errors':[]}
    unique = {}
    for scope, data in surface.items():
        report['surface'][scope] = data['counts']
        for row in data['differences']:
            path = canonical(row['path'])
            key = row['kind'] + ':' + path
            if key not in unique:
                interface = path.split('.')[1] if '.' in path else path
                unique[key] = {**row,'canonical_path':path,'owner':owner(interface),'scopes':[]}
            unique[key]['scopes'].append(scope)
    report['surface_unique_observations'] = len(unique)
    counts = Counter(row['owner'] for row in unique.values())
    report['owner_counts'] = dict(counts.most_common())
    phases = ('page-behavior',) if (folder/'page-behavior/metadata.json').is_file() else ('behavior','extended')
    for phase in phases:
        directory = folder/phase
        if not directory.is_dir():
            continue
        for reference in sorted(directory.glob('firefox-*.json')):
            suffix = reference.name[len('firefox-'):]
            current = directory/('ruyijs-'+suffix)
            if not current.exists():
                report['capture_errors'].append({'capture':suffix,'error':'Missing ruyijs capture'})
                continue
            left = json.loads(reference.read_text('utf-8'))
            right = json.loads(current.read_text('utf-8'))
            if not left.get('done') or not right.get('done') or left.get('error') or right.get('error'):
                report['capture_errors'].append({'capture':suffix,'firefox':left.get('error'),'ruyijs':right.get('error')})
            if suffix.startswith('worker-') and left.get('value') and right.get('value'):
                report['worker_surface'][suffix] = compare_surface(left['value']['surface'],right['value']['surface'])
                left,right=left['value']['behavior'],right['value']['behavior']
            else:
                left,right=left.get('value',left),right.get('value',right)
            rows = differences(left,right)
            report['behavior'][suffix] = {'differences':rows,'count':len(rows),
                'firefox_file':str(reference.relative_to(folder)), 'ruyijs_file':str(current.relative_to(folder))}
    trace_review = Path('D:/cf-turnstile-scrapingcourse/work/trace-review-20261025-223712/review.json')
    observed = set()
    if trace_review.exists():
        trace = json.loads(trace_review.read_text('utf-8'))
        for item in trace.get('apis',[]):
            interface, member, _ = item['api'].split('|')
            observed.add((interface,member.removeprefix('get ').removeprefix('set ')))
    for row in unique.values():
        match = re.match(r'interfaces\.([^.]+)(?:\.prototype)?\.(.+)',row['canonical_path'])
        row['observed_in_success_trace'] = bool(match and (match[1],match[2]) in observed)
    (folder/'surface-findings.json').write_text(json.dumps(list(unique.values()),ensure_ascii=False,indent=2)+'\n','utf-8')
    (folder/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    lines=['# Firefox / ruyijs 环境对照','',
        '本报告来自同一机器上的新 Firefox profile 和当前 ruyijs。接口数量相同不代表语义一致；以下计数按观测路径，不是独立缺陷数。','',
        '| 范围 | 缺失属性 | 多余属性 | 描述符差异 | 顺序差异 | 原型链差异 |',
        '|---|---:|---:|---:|---:|---:|']
    for scope,counts in report['surface'].items():
        lines.append('| '+scope+' | '+' | '.join(str(counts.get(k,0)) for k in
            ('missing_property','extra_property','descriptor','property_order','prototype_chain'))+' |')
    lines += ['', '## 同输入行为对照', '', '| 探针 / realm | 不同叶值数 |', '|---|---:|']
    for name,data in report['behavior'].items():
        lines.append(f"| {name.removesuffix('.json')} | {data['count']} |")
    lines += ['', '## 证据边界', '',
        '- surface 覆盖 HTTP/可信 localhost 的主 Window 和同源 iframe，并补充专用 Worker 的接口表。',
        '- behavior 覆盖 DOM、图形、平台值、realm、异常、网络、Worker、RTC、存储、调度、安全与观察器的固定输入。',
        '- 相同只表示已执行用例相同；权限 UI、真实媒体设备、WebTransport/WebSocket 外部服务、全部 CSS/codec 状态空间不在本轮行为覆盖内。',
        '- numeric fields use exact comparison; floating-point and timing differences require individual interpretation.',
        '- 原始结果与 metadata 保存版本、二进制 hash 和配置；完整逐项列表见 comparison.json 与 surface-findings.json。',
        '- 目标站点登录仍单独验收，本地环境对照不替代业务闭环。','']
    (folder/'REPORT.md').write_text('\n'.join(lines),'utf-8')
    print(json.dumps({'unique_surface_observations':len(unique),'behavior_cases':len(report['behavior']),
        'same_behavior_cases':sum(v['count']==0 for v in report['behavior'].values()),'capture_errors':len(report['capture_errors']),
        'trace_observed_surface_differences':sum(row['observed_in_success_trace'] for row in unique.values())}))


if __name__ == '__main__':
    main()
