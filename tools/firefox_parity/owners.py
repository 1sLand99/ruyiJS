"""Evidence-backed routing hints; this index is not an implementation owner approval."""
import re

DOCS = {
    "browser_environment": "BROWSER_ENVIRONMENT", "document_model": "DOCUMENT_MODEL",
    "execution_scheduling": "EXECUTION_SCHEDULING", "font_loading": "FONT_FACE",
    "interaction": "INTERACTION", "resource_network": "RESOURCE_NETWORK",
    "web_audio": "WEB_AUDIO", "web_broadcast": "BROADCAST_CHANNEL",
    "web_canvas": "WEB_CANVAS", "web_clipboard": "CLIPBOARD", "web_console": "CONSOLE",
    "web_credentials": "CREDENTIALS", "web_crypto": "CRYPTO", "web_geometry": "WEB_GEOMETRY",
    "web_gpu": "WEB_GPU", "web_graphics": "WEB_GRAPHICS", "web_indexeddb": "INDEXED_DB",
    "web_media": "MEDIA_DEVICES", "web_messaging": "MESSAGE_CHANNEL", "web_observers": "WEB_OBSERVERS",
    "web_permissions": "PERMISSIONS", "web_platform": "WEB_PLATFORM", "web_rtc": "WEB_RTC",
    "web_security": "CONTENT_SECURITY", "web_styling": "WEB_STYLING",
    "web_trusted_types": "TRUSTED_TYPES", "web_workers": "WORKER"}
RULES = [
    (r"^(WindowGlobal|Window|Navigator|Screen|Location|History|BarProp|Gamepad|Geolocation|Navigation|NavigatorLogin|External)", "browser_environment"),
    (r"^(Storage|FileSystem|Directory|Cache|CookieStore|Lock|Push)", "browser_environment"),
    (r"^(GPU)", "web_gpu"), (r"^(WebGL)", "web_graphics"),
    (r"^(Canvas|OffscreenCanvas|ImageBitmap|ImageData|Path2D)", "web_canvas"),
    (r"^(CSSStyleDeclaration|CSSStyleProperties)", "document_model"),
    (r"^(CSS|StyleSheet|MediaList|MediaQueryList|Animation|Keyframe|DocumentTimeline|Highlight|ViewTransition)", "web_styling"),
    (r"^(RTC)", "web_rtc"), (r"^(Audio|BaseAudio|OfflineAudio|Analyser|Biquad|Channel|Convolver|Delay|Dynamics|Gain|IIR|Oscillator|Panner|PeriodicWave|StereoPanner|WaveShaper)", "web_audio"),
    (r"^(Media|Video|Encoded|TextTrack|VTTCue|VTTRegion|TrackEvent|TimeRanges|Speech|MIDI|PictureInPicture|DocumentPictureInPicture|ImageDecoder|ImageTrack)", "web_media"),
    (r"^(Permission|WakeLock)", "web_permissions"),
    (r"^(Credential|Authenticator|PublicKey|Authentication|WebAuthn)", "web_credentials"),
    (r"^(Clipboard)", "web_clipboard"), (r"^(Crypto|SubtleCrypto)", "web_crypto"),
    (r"^(Trusted)", "web_trusted_types"), (r"^(IDB)", "web_indexeddb"),
    (r"^(Performance|IdleDeadline|Scheduler|TaskController|TaskSignal|TaskPriorityChangeEvent)", "execution_scheduling"),
    (r"^(Worker|SharedWorker|ServiceWorker|NavigationPreload|Worklet)", "web_workers"),
    (r"^(MessageChannel|MessagePort)", "web_messaging"), (r"^(BroadcastChannel)", "web_broadcast"),
    (r"^(Abort|Headers|Request|Response|XMLHttpRequest|EventSource|WebSocket|WebTransport|Readable|Writable|TransformStream|ByteLengthQueuing|CountQueuing)", "resource_network"),
    (r"^(URL|Blob|File$|FileList|FileReader|FormData|TextEncoder|TextDecoder|Compression|Decompression)", "web_platform"),
    (r"^(FontFace)", "font_loading"), (r"^(Resize|Intersection|MutationObserver|MutationRecord)", "web_observers"),
    (r"^(DOMPoint|DOMRect|DOMMatrix|DOMQuad)", "web_geometry"),
    (r"^(CSP|IntegrityViolation|SecurityPolicyViolation)", "web_security"),
    (r"^(Event|.*Event$|DataTransfer|Touch|CloseWatcher|InputDevice)", "interaction"),
    (r"^(HTML|SVG|MathMLElement|Node|Element|Document|ShadowRoot|Attr|CharacterData|Text$|Comment|Range|AbstractRange|StaticRange|Selection|TreeWalker|NamedNodeMap|DOMTokenList|DOMParser|DOMImplementation|DOMException|XML|XPath|XSLT|ProcessingInstruction|CustomElement|CustomState|ElementInternals|FragmentDirective|CaretPosition|Sanitizer|ValidityState|RadioNodeList)", "document_model"),
    (r"^(console|Console)", "web_console"),
    (r"^(Object|Function|Array|BigInt|Boolean|Number|String|Symbol|Math|JSON|Date|RegExp|Error|.*Error$|Map|Set|Weak|Promise|Proxy|Reflect|Intl|WebAssembly|Atomics|.*Array$|ArrayBuffer|SharedArrayBuffer|DataView|Iterator|DisposableStack|AsyncDisposableStack|TypedArray)", "engine_intrinsics")]


def source_index(root):
    index = {}
    for owner in DOCS:
        for path in (root / "src" / owner).glob("**/*"):
            if path.suffix not in (".cpp", ".h", ".js"):
                continue
            for name in set(re.findall(r'"([A-Za-z_$][A-Za-z0-9_$]*)"', path.read_text("utf-8", errors="replace"))):
                index.setdefault(name, {}).setdefault(owner, []).append(path.relative_to(root).as_posix())
    return index


def owner_record(object_name, property_name, index):
    name = object_name.removesuffix(".prototype")
    if name.startswith("instance:"):
        name = name.removeprefix("instance:")
        name = {"console": "Console", "location": "Location", "document": "Document",
                "navigator": "Navigator", "history": "History", "screen": "Screen",
                "performance": "Performance", "crypto": "Crypto", "customElements": "CustomElementRegistry",
                "localStorage": "Storage", "sessionStorage": "Storage", "visualViewport": "Window"}.get(name, name)
    if name == "WindowGlobal":
        name = property_name
        specials = {"caches": "Cache", "cookieStore": "CookieStore",
                    "documentPictureInPicture": "DocumentPictureInPicture", "speechSynthesis": "SpeechSynthesis",
                    "getDefaultComputedStyle": "CSS", "event": "Event"}
        name = specials.get(name, name)
        if name and (name[0].islower() or name.isdigit()):
            name = "Window"
    if name in ("CSS", "CSSStyleSheet"):
        hint = "web_styling"
    else:
        hint = next((owner for pattern, owner in RULES if re.match(pattern, name)), None)
    sources = index.get(name, {})
    if len(sources) == 1:
        owner = next(iter(sources))
        basis = "existing_source_literal"
    elif hint and hint in sources:
        owner, basis = hint, "existing_source_and_family"
    else:
        owner, basis = hint or "owner_review", "family_requires_owner_review"
    return {"owner": owner, "basis": basis,
            "ownerRecord": "docs/owners/" + DOCS[owner] + ".md" if owner in DOCS else None,
            "sources": sorted(sources.get(owner, []))[:3]}
