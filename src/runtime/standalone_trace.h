#ifndef RUYIJS_STANDALONE_TRACE_H
#define RUYIJS_STANDALONE_TRACE_H
// Firefox 158 sources have no SpiderMonkey call tracing. A donor built with it
// provides vm/StandaloneTrace.h, including the page's `ruyijs` helper object;
// otherwise tracing is off and runtime/host_helpers.cpp defines that object.
#include "js/CallArgs.h"
#if __has_include("vm/StandaloneTrace.h") && !defined(RUYIJS_NO_STANDALONE_TRACE)
#  include "vm/StandaloneTrace.h"
#  define RUYIJS_STANDALONE_TRACE 1
#endif

namespace ruyijs {
// Defines the `ruyijs` helper object as a property of |holder|.
bool DefineHostHelpers(JSContext* cx, JS::HandleObject holder);

namespace trace {
#ifdef RUYIJS_STANDALONE_TRACE
using CallState = js::standalone_trace::CallState;
inline bool Enabled() {
  return js::standalone_trace::IsEnabled(js::standalone_trace::Category::Ruyijs);
}
inline void EnterCall(JSContext* cx, const JS::CallArgs& args, bool constructing,
                      const char* entryPath, CallState* state) {
  js::standalone_trace::EnterCall(cx, args, constructing, entryPath, state);
}
inline void LeaveCall(JSContext* cx, const JS::CallArgs& args, const CallState& state, bool ok) {
  js::standalone_trace::LeaveCall(cx, args, state, ok);
}
#else
struct CallState {};
inline bool Enabled() { return false; }
inline void EnterCall(JSContext*, const JS::CallArgs&, bool, const char*, CallState*) {}
inline void LeaveCall(JSContext*, const JS::CallArgs&, const CallState&, bool) {}
#endif
}
}
#endif
