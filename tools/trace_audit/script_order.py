"""Extract an explicit interactive-boundary async-classic plan from a capture."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin


class AsyncScripts(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.urls = base, []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'script' and 'async' in attrs and 'src' in attrs and attrs.get('type') != 'module':
            url = urljoin(self.base, attrs['src'])
            if url in self.urls:
                raise ValueError('duplicate async URL requires occurrence-aware replay')
            self.urls.append(url)


def extract(packet_path, domtrace):
    packet = json.loads(packet_path.read_text('utf-8'))
    parser = AsyncScripts(packet['url'])
    body = packet['responseBody']
    if body.get('truncated') or not isinstance(body.get('text'), str):
        raise ValueError('document body must be complete text')
    parser.feed(body['text'])
    remaining, evidence, state_evidence = set(parser.urls), [], []
    active_url = None
    with domtrace.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row.get('type') == 'script_root':
                if row.get('phase') == 'start':
                    active_url = row.get('url')
                    if active_url in remaining:
                        if row.get('script_kind') != 'classic':
                            raise ValueError('selected root is not a classic script')
                        evidence.append({'url': active_url, 'line': number, 'seq': row['seq']})
                        remaining.remove(active_url)
                else:
                    active_url = None
            if row.get('interface') == 'Document' and row.get('member') == 'get readyState' and active_url in parser.urls:
                state_evidence.append({'line': number, 'url': active_url, 'value': row.get('value')})
            if not remaining and active_url is None:
                break
    if remaining:
        raise ValueError('selected async scripts have no recorded roots')
    if not state_evidence or any(row['value'] != 'interactive' for row in state_evidence):
        raise ValueError('capture does not support the interactive-boundary plan')
    result = {'schema': 'ruyijs.recorded-async-order.v1', 'urls': [row['url'] for row in evidence],
              'phase': 'interactive-before-deferred', 'evidence': evidence,
              'state_evidence': state_evidence,
              'limitations': 'Partial phase replay; intervening tasks and timing are not fully recorded.'}
    for name, path in [('document', packet_path), ('trace', domtrace)]:
        with path.open('rb') as stream:
            result[name] = {'path': str(path.resolve()), 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_packet', type=Path)
    parser.add_argument('domtrace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.document_packet, args.domtrace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps({'scripts': len(result['urls']), 'state_observations': len(result['state_evidence'])}))


if __name__ == '__main__':
    main()
