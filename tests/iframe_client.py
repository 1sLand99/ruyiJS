"""Actual C ABI adapter for the same iframe navigation cases as Python."""
import base64
import ctypes
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs._values import decode, JSError


class CClient:
    def __init__(self):
        self.directory = os.add_dll_directory(str(ROOT / 'dist'))
        self.dll = ctypes.CDLL(str(ROOT / 'dist/ruyijs_client.dll'))
        ptr = ctypes.c_void_p
        self.dll.ruyijs_create.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.POINTER(ptr)]
        self.dll.ruyijs_create.restype = ptr
        self.dll.ruyijs_call.argtypes = [ptr, ctypes.c_char_p, ctypes.c_uint32,
                                        ctypes.POINTER(ptr), ctypes.POINTER(ctypes.c_uint32)]
        self.dll.ruyijs_call.restype = ctypes.c_int
        self.dll.ruyijs_free.argtypes = [ptr]
        self.dll.ruyijs_close.argtypes = [ptr]
        error = ptr()
        shell = os.environ.get('RUYIJS_SHELL') or str(ROOT / 'dist/js.exe')
        self.context = self.dll.ruyijs_create(shell.encode('utf-8'), 15000, ctypes.byref(error))
        if not self.context:
            message = ctypes.string_at(error).decode('utf-8') if error else 'create failed'
            if error:
                self.dll.ruyijs_free(error)
            self.directory.close()
            raise RuntimeError(message)

    def call(self, op, **fields):
        data = json.dumps({'id': 1, 'op': op, **fields}).encode('utf-8')
        reply, length = ctypes.c_void_p(), ctypes.c_uint32()
        code = self.dll.ruyijs_call(self.context, data, len(data), ctypes.byref(reply), ctypes.byref(length))
        try:
            if code or not reply:
                raise RuntimeError('C ABI transport failure: ' + str(code))
            packet = json.loads(ctypes.string_at(reply, length.value))
            if not packet['ok']:
                error = packet['error']
                raise JSError(error['name'], error['message'], error.get('stack', ''))
            return decode(packet['value'])
        finally:
            if reply:
                self.dll.ruyijs_free(reply)

    def eval(self, code):
        return self.call('eval', code=code)

    def load_page(self, url, html):
        return self.call('page', action='load', url=url, html=html)

    def put_resource(self, url, body, status=200, headers=None):
        return self.call('resource', action='put', url=url, status=status, headers=headers or [],
                         body={'kind': 'text', 'base64': base64.b64encode(body.encode()).decode()})

    def configure_clock(self, mode, epoch_ms):
        return self.call('event_loop', action='configure', mode=mode, epoch_ms=epoch_ms)

    def advance(self, ms):
        return self.call('event_loop', action='advance', ms=ms)

    def net_log(self):
        return self.call('resource', action='log')['entries']

    def close(self):
        if self.context:
            self.dll.ruyijs_close(self.context)
            self.context = None
            self.directory.close()
