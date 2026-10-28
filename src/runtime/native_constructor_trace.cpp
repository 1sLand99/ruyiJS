#include "runtime/native_constructor_trace.h"
#include "js/Exception.h"

namespace ruyijs {
NativeConstructorTrace::NativeConstructorTrace(JSContext* cx, const JS::CallArgs& args)
    : cx_(cx), args_(args) {
  enabled_ = args.isConstructing() &&
      trace::Enabled();
  if (enabled_)
    trace::EnterCall(cx_, args_, true, "native-constructor", &state_);
}
NativeConstructorTrace::~NativeConstructorTrace() {
  if (enabled_)
    trace::LeaveCall(cx_, args_, state_, ok_ && !JS_IsExceptionPending(cx_));
}
}
