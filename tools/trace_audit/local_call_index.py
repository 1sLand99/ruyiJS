"""Read-only index of one synchronous fixture's JSCT records in leave order."""
from collections import Counter
import mmap

from .binary import CALL, HEADER, header
from .jsonlines import dictionary


class CallIndex:
    def __init__(self, binary, dictionary_path):
        self.functions, self.stats, errors = dictionary(dictionary_path)
        if errors or not self.stats: raise ValueError('missing or malformed dictionary')
        if any(self.stats.get(k,0) for k in ('dropped_limit','dropped_gate','dropped_no_func_id','dropped_chunks','io_errors')):
            raise ValueError('capture reports loss')
        self.stream = binary.open('rb')
        self.data = None
        try:
            self.pid = header(self.stream,b'JSCT',CALL.size)
            self.data = mmap.mmap(self.stream.fileno(),0,access=mmap.ACCESS_READ)
            if (len(self.data)-HEADER.size)%CALL.size: raise ValueError('incomplete call record')
            self.offsets = {}
            self.counts = Counter()
            threads = set()
            for offset in range(HEADER.size,len(self.data),CALL.size):
                call,parent,fn,duration,depth,argc,flags,entry,reserved = CALL.unpack_from(self.data,offset)
                if not call or call in self.offsets: raise ValueError('zero or duplicate call id')
                if fn not in self.functions: raise ValueError('unknown function')
                if parent and (parent>=call or parent>>48!=call>>48): raise ValueError('invalid parent id')
                if reserved or flags&~127 or entry not in range(1,5): raise ValueError('unknown call encoding')
                if not flags&2 or flags&(1|4|8|16|32): raise ValueError('fixture requires successful synchronous JS calls')
                self.offsets[call] = offset
                self.counts[self.functions[fn]['name']] += 1
                threads.add(call>>48)
            if len(threads)!=1: raise ValueError('local fixture requires exactly one observed JS thread')
            if len(self.offsets)!=self.stats['recorded']: raise ValueError('writer count mismatch')
            self.edges = Counter()
            self.gaps = 0
            for call,offset in self.offsets.items():
                row = self.row(call)
                parent = row['parent']
                self.gaps += row['gap']
                if parent:
                    if parent not in self.offsets: raise ValueError('missing parent')
                    ancestor = self.row(parent)
                    if self.offsets[parent]<=offset: raise ValueError('parent did not leave after child')
                    if row['depth']!=ancestor['depth']+1: raise ValueError('observed parent depth mismatch')
                    self.edges[(ancestor['name'],row['name'])] += 1
                elif row['depth']!=1:
                    raise ValueError('unexpected fixture root depth')
        except BaseException:
            self.close()
            raise

    def row(self, call):
        offset = self.offsets.get(call)
        if offset is None: raise ValueError('value references missing call')
        identity,parent,fn,duration,depth,argc,flags,entry,reserved = CALL.unpack_from(self.data,offset)
        return {'id':identity,'parent':parent,'name':self.functions[fn]['name'],
                'depth':depth,'argc':argc,'gap':bool(flags&64),'leave_offset':offset}

    def close(self):
        if self.data is not None: self.data.close(); self.data=None
        self.stream.close()

    def __enter__(self): return self
    def __exit__(self,*_): self.close()
