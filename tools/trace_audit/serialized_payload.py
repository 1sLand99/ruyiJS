"""Recover complete serialized JSON from captured arrays or serializer call spans."""
import json
import math


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def primitive(value):
    kind = value['type']
    if kind == 'null': return None
    if kind not in ('string', 'number', 'boolean') or 'value' not in value:
        raise ValueError('missing complete primitive value')
    result = value['value']
    if kind == 'boolean' and type(result) is not bool:
        raise ValueError('invalid boolean capture')
    if kind == 'string':
        if not isinstance(result, str) or len(result.encode('utf-16-le', 'surrogatepass')) // 2 != value['length']:
            raise ValueError('string length or capture mismatch')
    if kind == 'number':
        if type(result) not in (int, float) or not math.isfinite(result):
            raise ValueError('unsupported number representation')
        if result == int(result): result = int(result)
    return result


def reconstruct(rows, function, column):
    stack, roots = [], []
    for row in rows:
        if row.get('type') != 'jscall' or row.get('callee') != function: continue
        if row.get('phase') == 'enter':
            if row.get('column') != column: continue
            args = row['args']
            if row.get('args_truncated') or len(args) < 3 or args[2].get('type') != 'number':
                raise ValueError('missing serializer offset')
            start = args[2]['value']
            if type(start) is not int or start < 0: raise ValueError('invalid start offset')
            node = {'call_id': row['call_id'], 'start': start, 'input': args[0], 'children': [],
                    'file_line': row.get('file_line')}
            if stack: stack[-1]['children'].append(node)
            else: roots.append(node)
            stack.append(node)
        elif row.get('phase') == 'leave':
            if not stack or stack[-1]['call_id'] != row['call_id']:
                raise ValueError('unbalanced serializer calls')
            node = stack.pop()
            if row.get('completion') != 'return' or row['result'].get('type') != 'number':
                raise ValueError('serializer did not return an offset')
            node['end'] = row['result']['value']
            if type(node['end']) is not int or node['end'] < node['start']:
                raise ValueError('invalid end offset')
    if stack: raise ValueError('incomplete serializer call')
    if len(roots) != 1: raise ValueError('expected one serializer root')

    def build(node):
        value, children = node['input'], node['children']
        if value['type'] != 'object':
            if children: raise ValueError('primitive contains serializer children')
            result = primitive(value)
        elif value.get('class') == 'Object':
            if len(children) % 2: raise ValueError('object key/value pairs incomplete')
            result = {}
            cursor = node['start'] + 1
            for n in range(0, len(children), 2):
                key_node, value_node = children[n:n+2]
                if key_node['start'] != cursor: raise ValueError('object key offset mismatch')
                key = build(key_node)
                if not isinstance(key, str) or key in result: raise ValueError('invalid or duplicate object key')
                if value_node['start'] != key_node['end'] + 1: raise ValueError('missing object separator')
                result[key] = build(value_node)
                cursor = value_node['end'] + (1 if n+2 < len(children) else 0)
            if cursor != node['end'] - 1: raise ValueError('object closing offset mismatch')
        elif value.get('class') == 'Array':
            result = []; cursor = node['start'] + 1
            for n, child in enumerate(children):
                if child['start'] != cursor: raise ValueError('array element offset mismatch')
                result.append(build(child));cursor = child['end'] + (1 if n+1 < len(children) else 0)
            if cursor != node['end'] - 1: raise ValueError('array closing offset mismatch')
        else: raise ValueError('unsupported object serialization')
        if len(encode(result)) != node['end'] - node['start']:
            raise ValueError('serialized byte span does not match recorded offsets')
        return result

    value = build(roots[0])
    return value, {'root_call_id': roots[0]['call_id'], 'start': roots[0]['start'],
                   'end': roots[0]['end'], 'serializer_calls': sum(row.get('phase') == 'enter'
                   and row.get('callee') == function and row.get('column') == column for row in rows)}


def differences(left, right, path=''):
    if type(left) is not type(right): return [{'path': path, 'reference': left, 'replay': right}]
    if isinstance(left, dict):
        result = []
        for key in dict.fromkeys([*left, *right]):
            child = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in left or key not in right:
                result.append({'path': child, 'reference_present': key in left, 'replay_present': key in right,
                               'reference': left.get(key), 'replay': right.get(key)})
            else: result.extend(differences(left[key], right[key], child))
        return result
    if isinstance(left, list):
        if len(left) != len(right): return [{'path': path, 'reference': left, 'replay': right}]
        return [item for n, (a, b) in enumerate(zip(left, right)) for item in differences(a, b, path+'/'+str(n))]
    return [] if left == right else [{'path': path, 'reference': left, 'replay': right}]
