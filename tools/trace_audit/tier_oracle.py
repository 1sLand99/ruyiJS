"""Independent integer/output oracle for the published tier fixture only."""
from functools import lru_cache


def int32(value):
    value &= 0xffffffff
    return value - (1<<32) if value & (1<<31) else value


@lru_cache(maxsize=300000)
def leaf(value):
    for step in range(32):
        value = int32((value*33) ^ ((value & 0xffffffff)>>3) ^ step)
    return value


EXPECTED_PARENTS = {'':{None}, 'surface':{None}, 'run':{None}, 'acceptOnly':{'surface'},
    'measuredLeaf':{'run','shiftedOne','shiftedTwo'}, 'shiftedOne':{'run'},
    'shiftedTwo':{'run'}, 'measuredBytes':{'run'}}


class TierOracle:
    def __init__(self, expected_runs, complete):
        self.expected_runs = expected_runs
        self.complete = complete
        self.run_index = 0
        self.checks = {'numeric_returns':0,'leaf_returns':0,'byte_returns':0,
                       'wrapper_returns':0,'run_checksums':0,'unknown_object_contents':0}
        self.active_run = None
        self.recovered_runs = []

    def enter(self, frame, parent):
        name = frame['name']
        if name not in EXPECTED_PARENTS or (parent['name'] if parent else None) not in EXPECTED_PARENTS[name]:
            raise ValueError('fixture call edge differs from source topology')
        frame['children'] = 0
        if parent: parent['children'] += 1
        if name=='run':
            if self.run_index>=len(self.expected_runs): raise ValueError('unexpected extra benchmark run')
            frame['expected'] = self.expected_runs[self.run_index]
            frame['leaf_count'] = frame['byte_count'] = frame['checksum'] = 0
            self.run_index += 1
            self.active_run = frame
        elif name in ('measuredLeaf','shiftedOne','shiftedTwo','measuredBytes'):
            if self.active_run is None: raise ValueError('workload call outside benchmark root')
            frame['iteration'] = self.active_run['leaf_count']

    def leave(self, frame, parent):
        name,args,result = frame['name'],frame['args'],frame['result']
        expected_args=2 if name=='run' else 0 if name in ('','surface') else 1
        if set(args)!=set(range(expected_args)): raise ValueError('fixture argument slots incomplete')
        if frame['argc']!=expected_args: raise ValueError('call argc mismatch')
        if name in ('measuredLeaf','shiftedOne','shiftedTwo'):
            if type(args[0]) is not int or type(result) is not int:
                raise ValueError('expected exact integer arithmetic values')
            increment={'measuredLeaf':0,'shiftedOne':1,'shiftedTwo':2}[name]
            if result!=leaf(args[0]+increment): raise ValueError('arithmetic return differs')
            self.checks['numeric_returns'] += 1
            if name=='measuredLeaf':
                self.checks['leaf_returns'] += 1
                run=self.active_run
                if self.complete:
                    n=run['leaf_count'];wanted_parent=('run','shiftedOne','shiftedTwo')[n%3]
                    if parent['name']!=wanted_parent or args[0]!=n+n%3 or run['byte_count']:
                        raise ValueError('leaf input/order differs from known workload')
                    if frame['children']: raise ValueError('leaf unexpectedly calls script functions')
                run['leaf_count'] += 1
                run['checksum'] = int32(run['checksum'] ^ result)
            else:
                self.checks['wrapper_returns'] += 1
                if self.complete and (args[0]!=frame['iteration'] or frame['iteration']%3!=increment or frame['children']!=1):
                    raise ValueError('wrapper input or child count differs')
        elif name=='measuredBytes':
            if args[0]!=('bytes',bytes(1024)) or result!=1024:
                raise ValueError('buffer argument/return differs')
            self.checks['numeric_returns'] += 1; self.checks['byte_returns'] += 1
            self.active_run['byte_count'] += 1
        elif name=='acceptOnly':
            if args[0] not in (('label','Object'),('label','Proxy')) or result!='object':
                raise ValueError('surface probe call differs')
            self.checks['unknown_object_contents'] += 1
        elif name=='':
            if result!=('undefined',): raise ValueError('fixture initialization return differs')
        elif name=='surface':
            if result!=('label','Object') or frame['children']!=2:
                raise ValueError('surface probe call structure differs')
            self.checks['unknown_object_contents'] += 1
        elif name=='run':
            expected=frame['expected']
            if any(type(value) is not int for value in args.values()):
                raise ValueError('benchmark arguments must retain integer type')
            if [args[0],args[1]]!=expected['arguments']: raise ValueError('benchmark run arguments differ')
            if result!=('label','Object'): raise ValueError('run return has unexpected representation')
            if self.complete:
                if [frame['leaf_count'],frame['byte_count']]!=expected['arguments']:
                    raise ValueError('missing benchmark work')
                if [frame['checksum'],frame['byte_count']*1024]!=expected['checksum']:
                    raise ValueError('record-derived checksum differs from actual page')
                self.checks['run_checksums'] += 1
                self.recovered_runs.append({'arguments':[args[0],args[1]],
                    'checksum':[frame['checksum'],frame['byte_count']*1024],
                    'run_call_id':frame['id']})
            self.checks['unknown_object_contents'] += 1
            self.active_run = None

    def finish(self):
        if self.active_run or self.run_index!=len(self.expected_runs):
            raise ValueError('benchmark run boundaries incomplete')
        return {**self.checks,'recovered_runs':self.recovered_runs}
