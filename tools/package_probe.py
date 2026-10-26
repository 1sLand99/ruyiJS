"""Executed in a fresh isolated Python process against relocated package files."""

import ctypes
import json
import os
import sys
from pathlib import Path


def main():
    package = Path(sys.argv[1]).resolve()
    assert not any(key.upper().startswith("RUYIJS") for key in os.environ)
    assert Path.cwd() == Path(os.environ["SystemRoot"])
    sys.path.insert(0, str(package / "python"))
    from ruyijs import Context, JSError
    import ruyijs
    assert Path(ruyijs.__file__).resolve().is_relative_to(package)
    with Context(timeout=10) as context:
        assert context.shell == package / "dist/js.exe"
        assert context.eval("40+2") == 42
        assert context.eval("globalThis.saved='迁移 空格'; saved") == "迁移 空格"
        assert context.eval("saved") == "迁移 空格"
        assert context.eval("typeof read") == "undefined"
        try:
            context.eval("throw new Error('relocation')")
        except JSError:
            pass
        else:
            raise AssertionError("expected JavaScript error")
        assert context.eval("6*7") == 42
    with Context(timeout=10) as context:
        context.configure_clock("logical", epoch_ms=1700000000000)
        # A new browsing context owns startup work (the speech owner's voice
        # publication task); run it first so the timers below are the only tasks.
        state = context.advance(1)
        assert state["now_ms"] == 1 and state["pending"] == 0, state
        context.eval("globalThis.order=[];setTimeout(()=>{order.push('timer');"
                     "queueMicrotask(()=>order.push('microtask'))},10);"
                     "setTimeout(()=>order.push('later'),20);undefined")
        state = context.advance(100, max_tasks=1)
        assert state["exhausted"] is True and state["now_ms"] == 11
        assert context.eval("[order,Date.now()]") == [["timer", "microtask"], 1700000000011]
        state = context.advance(10)
        assert state["exhausted"] is False and state["pending"] == 0
        assert context.eval("order") == ["timer", "microtask", "later"]
        context.put_resource("/relocated", b"\x00\xff", status=201,
                             headers=[["Set-Cookie", "a=1"], ["set-cookie", "b=2"]])
        resource = context.get_resource("/relocated?v=1")
        assert resource["body"] == b"\x00\xff" and resource["status"] == 201
        assert resource["headers"] == [["set-cookie", "a=1"], ["set-cookie", "b=2"]]
        assert context.eval("new Headers([['X','one'],['x','two']]).get('x')") == "one, two"
        assert context.clear_resources() == {"resources": 0, "bytes": 0}
    with os.add_dll_directory(str(package / "dist")):
        dll = ctypes.CDLL(str(package / "dist/ruyijs_client.dll"))
        for name in ("ruyijs_create", "ruyijs_call", "ruyijs_free", "ruyijs_close",
                     "ruyijs_set_callback", "ruyijs_alloc"):
            getattr(dll, name)
        pointer = ctypes.c_void_p
        dll.ruyijs_create.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.POINTER(pointer)]
        dll.ruyijs_create.restype = pointer
        dll.ruyijs_call.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32,
                                    ctypes.POINTER(pointer), ctypes.POINTER(ctypes.c_uint32)]
        dll.ruyijs_call.restype = ctypes.c_int
        dll.ruyijs_free.argtypes = [pointer]
        dll.ruyijs_close.argtypes = [pointer]
        error = pointer()
        context = dll.ruyijs_create(str(package / "dist/js.exe").encode("utf-8"),
                                   10000, ctypes.byref(error))
        if not context:
            message = ctypes.string_at(error).decode("utf-8") if error else "create failed"
            if error:
                dll.ruyijs_free(error)
            raise AssertionError(message)
        def call(**fields):
            request = json.dumps({"id": 1, **fields}).encode("utf-8")
            reply, length = pointer(), ctypes.c_uint32()
            status = dll.ruyijs_call(context, request, len(request), ctypes.byref(reply),
                                     ctypes.byref(length))
            assert status == 0 and reply
            try:
                value = json.loads(ctypes.string_at(reply, length.value).decode("utf-8"))
                assert value["ok"] is True, value
                return value["value"]
            finally:
                dll.ruyijs_free(reply)
        try:
            call(op="event_loop", action="configure", mode="logical", epoch_ms=1700000000000)
            assert call(op="eval", code="21*2") == {"type": "number", "value": 42}
            call(op="eval", code="globalThis.t=0;setTimeout(()=>t=Date.now(),10);undefined")
            state = call(op="event_loop", action="advance", ms=10)
            assert state["type"] == "object"
            assert dict(state["value"])["exhausted"] == {"type": "boolean", "value": False}
            assert call(op="eval", code="t") == {"type": "number", "value": 1700000000010}
            state = call(op="resource", action="put", url="/c",
                         body={"kind": "bytes", "base64": "AP8="})
            assert dict(state["value"])["resources"] == {"type": "number", "value": 1}
            resource = call(op="resource", action="get", url="/c?relocated=1")
            body = dict(dict(resource["value"])["body"]["value"])
            assert body["kind"] == {"type": "string", "value": "bytes"}
            assert body["base64"] == {"type": "string", "value": "AP8="}
            assert call(op="eval", code="new Headers({x:'c'}).get('x')") == {"type": "string", "value": "c"}
        finally:
            dll.ruyijs_close(context)
    print(json.dumps({"python": "passed", "c_abi": "passed", "cwd": str(Path.cwd()),
                      "scheduling": "passed", "resources_and_headers": "passed",
                      "python_module": ruyijs.__file__,
                      "ruyijs_overrides": []}))


if __name__ == "__main__":
    main()
