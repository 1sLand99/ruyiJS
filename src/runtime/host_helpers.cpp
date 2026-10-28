// The page's `ruyijs` helper object. A donor with SpiderMonkey call tracing
// defines it (js::standalone_trace::DefineRuyijsObject); for Firefox sources
// without tracing this is the same object with its tracing members inert.
#include "runtime/standalone_trace.h"

#ifdef RUYIJS_STANDALONE_TRACE
namespace ruyijs {
bool DefineHostHelpers(JSContext* cx, JS::HandleObject holder) {
  return js::standalone_trace::DefineRuyijsObject(cx, holder);
}
}
#else
#include "jsapi.h"
#include "jsfriendapi.h"
#include "js/CallAndConstruct.h"
#include "js/CharacterEncoding.h"
#include "js/Conversions.h"
#include "js/PropertyAndElement.h"
#include "js/Proxy.h"
#include "vm/JSObject.h"
#include "vm/PlainObject.h"
#include "vm/StringType.h"
#include "vm/JSObject-inl.h"
#include <cstdint>

namespace ruyijs {
namespace {
const JSErrorFormatString* HostReceiverError(void*, unsigned) {
  static const JSErrorFormatString format = {
      "HOST_INVALID_RECEIVER", "{0}", 1, JSEXN_TYPEERR};
  return &format;
}

bool HostFunctionCall(JSContext* cx, unsigned argc, JS::Value* vp) {
  JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
  JS::RootedObject callee(cx, &args.callee());
  JS::RootedValue implementation(cx, js::GetFunctionNativeReserved(callee, 0));
  JS::RootedValue receiver(cx);
  JS::RootedObject instance(cx);
  if (args.isConstructing()) {
    JS::RootedObject newTarget(cx, &args.newTarget().toObject());
    JS::RootedObject proto(cx);
    if (!js::GetPrototypeFromConstructor(cx, newTarget, JSProto_Object, &proto)) return false;
    instance = proto ? js::NewPlainObjectWithProto(cx, proto) : js::NewPlainObject(cx);
    if (!instance) return false;
    receiver.setObject(*instance);
  } else {
    receiver = args.thisv();
  }
  JS::RootedValue receiverCheck(cx, js::GetFunctionNativeReserved(callee, 1));
  if (!receiverCheck.isUndefined()) {
    JS::RootedValue error(cx);
    if (!JS::Call(cx, receiver, receiverCheck, JS::HandleValueArray::empty(), &error))
      return false;
    if (!error.isUndefined()) {
      if (!error.isString()) {
        JS_ReportErrorASCII(cx, "Host receiver check must return undefined or an error message");
        return false;
      }
      JS::RootedString message(cx, error.toString());
      JS::UniqueChars utf8 = JS_EncodeStringToUTF8(cx, message);
      if (!utf8) return false;
      JS_ReportErrorNumberUTF8(cx, HostReceiverError, nullptr, 0, utf8.get());
      return false;
    }
  }
  bool ok = JS::Call(cx, receiver, implementation, JS::HandleValueArray(args), args.rval());
  if (ok && instance && !args.rval().isObject()) args.rval().setObject(*instance);
  return ok;
}

// ruyijs.createHostFunction(fn, name[, length, constructor, receiverCheck])
bool CreateHostFunction(JSContext* cx, unsigned argc, JS::Value* vp) {
  JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
  JS::UniqueChars name;
  if (args.length() >= 2 && args[1].isString()) {
    JS::RootedString text(cx, args[1].toString());
    name = JS_EncodeStringToUTF8(cx, text);
    if (!name) return false;
  }
  if (!name || !args[0].isObject() || !args[0].toObject().isCallable()) {
    JS_ReportErrorASCII(cx,
        "usage: ruyijs.createHostFunction(fn, name[, length, constructor, receiverCheck])");
    return false;
  }
  uint32_t length = 0;
  if (args.length() > 2 && !JS::ToUint32(cx, args[2], &length)) return false;
  if (length > UINT16_MAX) {
    JS_ReportErrorASCII(cx, "ruyijs.createHostFunction: length exceeds 65535");
    return false;
  }
  unsigned flags = args.length() > 3 && JS::ToBoolean(args[3]) ? JSFUN_CONSTRUCTOR : 0;
  if (args.length() > 4 && !args[4].isUndefined() &&
      (!args[4].isObject() || !args[4].toObject().isCallable())) {
    JS_ReportErrorASCII(cx, "ruyijs.createHostFunction: receiverCheck must be callable");
    return false;
  }
  JS::RootedFunction function(
      cx, js::NewFunctionWithReserved(cx, HostFunctionCall, length, flags, name.get()));
  if (!function) return false;
  JS::RootedObject object(cx, JS_GetFunctionObject(function));
  js::SetFunctionNativeReserved(object, 0, args[0]);
  js::SetFunctionNativeReserved(object, 1, args.length() > 4 ? args[4] : JS::UndefinedValue());
  args.rval().setObject(*object);
  return true;
}

class HostCollectionHandler final : public js::ForwardingProxyHandler {
  static const char family;
  bool isProtected(JSContext* cx, JS::HandleObject proxy, JS::HandleId id, bool* found) const {
    JS::RootedObject names(cx, &js::GetProxyReservedSlot(proxy, 0).toObject());
    return JS_HasOwnPropertyById(cx, names, id, found);
  }
 public:
  HostCollectionHandler() : js::ForwardingProxyHandler(&family) {}
  bool defineProperty(JSContext* cx, JS::HandleObject proxy, JS::HandleId id,
                      JS::Handle<JS::PropertyDescriptor> desc,
                      JS::ObjectOpResult& result) const override {
    // WebIDL legacy platform objects without an indexed setter reject indices.
    uint32_t index;
    if (id.isInt() || (id.isAtom() && id.toAtom()->isIndex(&index)))
      return result.failNoIndexedSetter();
    bool protectedName;
    if (!isProtected(cx, proxy, id, &protectedName)) return false;
    if (protectedName) return result.failNoNamedSetter();
    return js::ForwardingProxyHandler::defineProperty(cx, proxy, id, desc, result);
  }
  bool delete_(JSContext* cx, JS::HandleObject proxy, JS::HandleId id,
               JS::ObjectOpResult& result) const override {
    // WebIDL [[Delete]] rejects supported indices and names without a deleter.
    bool protectedName;
    if (!isProtected(cx, proxy, id, &protectedName)) return false;
    if (protectedName) return result.failCantDelete();
    return js::ForwardingProxyHandler::delete_(cx, proxy, id, result);
  }
  bool preventExtensions(JSContext*, JS::HandleObject, JS::ObjectOpResult& result) const override {
    // WebIDL legacy platform objects are always extensible.
    return result.failCantPreventExtensions();
  }
};
const char HostCollectionHandler::family = 0;
const HostCollectionHandler hostCollectionHandler;
const JSClass hostCollectionClass = PROXY_CLASS_DEF("HostCollection", JSCLASS_HAS_RESERVED_SLOTS(1));

// ruyijs.createHostCollection(backing, names)
bool CreateHostCollection(JSContext* cx, unsigned argc, JS::Value* vp) {
  JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
  if (args.length() != 2 || !args[0].isObject() || !args[1].isObject() ||
      !args[0].toObject().is<js::PlainObject>() || !args[1].toObject().is<js::PlainObject>()) {
    JS_ReportErrorASCII(cx, "usage: ruyijs.createHostCollection(backing, names)");
    return false;
  }
  js::ProxyOptions options;
  options.setClass(&hostCollectionClass).setLazyProto(true);
  JS::RootedObject object(cx, js::NewProxyObject(cx, &hostCollectionHandler, args[0], nullptr, options));
  if (!object) return false;
  // Private and reserved slots trace the backing object and mutable name registry.
  js::SetProxyReservedSlot(object, 0, args[1]);
  args.rval().setObject(*object);
  return true;
}

// Without tracing: enabled() and makeConfigurable() report false, and the
// register* members, which only name host members in trace records, do nothing.
bool Disabled(JSContext* cx, unsigned argc, JS::Value* vp) {
  JS::CallArgsFromVp(argc, vp).rval().setBoolean(false);
  return true;
}
bool Ignored(JSContext* cx, unsigned argc, JS::Value* vp) {
  JS::CallArgsFromVp(argc, vp).rval().setUndefined();
  return true;
}
bool RegisterInterface(JSContext* cx, unsigned argc, JS::Value* vp) {
  JS::CallArgsFromVp(argc, vp).rval().setInt32(0);
  return true;
}

const JSFunctionSpec helperFunctions[] = {
    JS_FN("enabled", Disabled, 0, 0),
    JS_FN("createHostFunction", CreateHostFunction, 2, 0),
    JS_FN("createHostCollection", CreateHostCollection, 2, 0),
    JS_FN("registerMember", Ignored, 3, 0),
    JS_FN("registerObject", Ignored, 2, 0),
    JS_FN("registerInterface", RegisterInterface, 2, 0),
    JS_FN("makeConfigurable", Disabled, 2, 0),
    JS_FS_END,
};
}

bool DefineHostHelpers(JSContext* cx, JS::HandleObject holder) {
  JS::RootedObject object(cx, JS_NewPlainObject(cx));
  return object && JS_DefineFunctions(cx, object, helperFunctions) &&
         JS_DefineProperty(cx, object, "hostFunctionReceiverChecks",
                           JS::TrueHandleValue, JSPROP_READONLY | JSPROP_PERMANENT) &&
         JS_DefineProperty(cx, holder, "ruyijs", object, 0);
}
}
#endif
