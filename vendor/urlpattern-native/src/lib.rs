//! ruyijs C ABI over the Firefox-vendored `urlpattern` 0.6.0 crate.
//!
//! Ported from Firefox `netwerk/base/urlpattern_glue` (helpers.rs, lib.rs): the
//! same constructor-string/init processing, ECMAScript regexp syntax and
//! component matcher, with Gecko string/array types replaced by UTF-8 buffers
//! and a C++ sink. Regular expressions are compiled and executed by the
//! embedding SpiderMonkey (ruyijs_urlpattern_regexp_*); no JS object is held
//! here, so dropping a pattern never touches the engine.
use std::borrow::Cow;
use std::ffi::c_void;
use url::Url;
use urlpattern::parser::RegexSyntax;
use urlpattern::quirks;
use urlpattern::regexp::RegExp;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct RyStr {
    pub ptr: *const u8,
    pub len: usize,
    pub valid: bool,
}

impl RyStr {
    fn none() -> Self {
        RyStr { ptr: std::ptr::null(), len: 0, valid: false }
    }
    fn of(s: &str) -> Self {
        RyStr { ptr: s.as_ptr(), len: s.len(), valid: true }
    }
    unsafe fn get(&self) -> Option<&str> {
        if !self.valid {
            return None;
        }
        if self.len == 0 {
            return Some("");
        }
        Some(std::str::from_utf8_unchecked(std::slice::from_raw_parts(self.ptr, self.len)))
    }
}

/// protocol, username, password, hostname, port, pathname, search, hash, baseURL.
#[repr(C)]
pub struct RyInit {
    pub fields: [RyStr; 9],
}

extern "C" {
    fn ruyijs_urlpattern_regexp_valid(pattern: *const u16, len: usize, ignore_case: bool) -> bool;
    fn ruyijs_urlpattern_regexp_exec(pattern: *const u16, len: usize, ignore_case: bool, text: *const u8,
                                     text_len: usize, match_only: bool, matched: *mut bool,
                                     captures: *mut c_void) -> bool;
    fn ruyijs_urlpattern_sink(sink: *mut c_void, value: RyStr);
}

/// Called by ruyijs_urlpattern_regexp_exec for each capture (index 1..).
#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_push_capture(captures: *mut c_void, value: RyStr) {
    let list = &mut *(captures as *mut Vec<Option<String>>);
    list.push(value.get().map(|s| s.to_owned()));
}

pub struct SmRegexp(String, bool);

fn regexp_exec(re: &SmRegexp, text: &str, match_only: bool) -> Option<Vec<Option<String>>> {
    let pattern16: Vec<u16> = re.0.encode_utf16().collect();
    let mut matched = false;
    let mut captures: Vec<Option<String>> = Vec::new();
    let ok = unsafe {
        ruyijs_urlpattern_regexp_exec(pattern16.as_ptr(), pattern16.len(), re.1, text.as_ptr(), text.len(),
                                      match_only, &mut matched,
                                      &mut captures as *mut Vec<Option<String>> as *mut c_void)
    };
    if !ok || !matched {
        return None;
    }
    Some(captures)
}

impl RegExp for SmRegexp {
    fn syntax() -> RegexSyntax {
        RegexSyntax::EcmaScript
    }
    fn parse(pattern: &str, flags: &str, _force_eval: bool) -> Result<Self, ()> {
        let ignore_case = flags.contains('i');
        let pattern16: Vec<u16> = pattern.encode_utf16().collect();
        if unsafe { ruyijs_urlpattern_regexp_valid(pattern16.as_ptr(), pattern16.len(), ignore_case) } {
            Ok(SmRegexp(pattern.to_string(), ignore_case))
        } else {
            Err(())
        }
    }
    // As in Firefox: only used while parsing (special-scheme protocol check).
    fn matches<'a>(&self, text: &'a str) -> Option<Vec<Option<&'a str>>> {
        regexp_exec(self, text, false).map(|_| vec![None])
    }
    fn pattern_string(&self) -> &str {
        &self.0
    }
}

type Pattern = urlpattern::UrlPattern<SmRegexp>;
type Component = urlpattern::component::Component<SmRegexp>;
type Matcher = urlpattern::matcher::Matcher<SmRegexp>;
type InnerMatcher = urlpattern::matcher::InnerMatcher<SmRegexp>;

fn owned(s: &RyStr) -> Option<String> {
    unsafe { s.get().map(|v| v.to_owned()) }
}

fn lib_init(init: &RyInit) -> urlpattern::UrlPatternInit {
    let f = &init.fields;
    let base_url = match owned(&f[8]) {
        Some(s) if !s.is_empty() => Url::parse(&s).ok(),
        _ => None,
    };
    urlpattern::UrlPatternInit {
        protocol: owned(&f[0]), username: owned(&f[1]), password: owned(&f[2]), hostname: owned(&f[3]),
        port: owned(&f[4]), pathname: owned(&f[5]), search: owned(&f[6]), hash: owned(&f[7]), base_url,
    }
}

fn quirks_init(init: &RyInit) -> quirks::UrlPatternInit {
    let f = &init.fields;
    quirks::UrlPatternInit {
        protocol: owned(&f[0]), username: owned(&f[1]), password: owned(&f[2]), hostname: owned(&f[3]),
        port: owned(&f[4]), pathname: owned(&f[5]), search: owned(&f[6]), hash: owned(&f[7]),
        base_url: owned(&f[8]),
    }
}

fn parse_from_init(init: urlpattern::UrlPatternInit, ignore_case: bool) -> *mut c_void {
    let options = urlpattern::UrlPatternOptions { regex_syntax: RegexSyntax::EcmaScript, ignore_case };
    match quirks::parse_pattern_as_lib::<SmRegexp>(init, options) {
        Ok(pattern) => Box::into_raw(Box::new(pattern)) as *mut c_void,
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_parse_string(input: RyStr, base: RyStr, ignore_case: bool) -> *mut c_void {
    let Some(text) = input.get() else { return std::ptr::null_mut() };
    let base_url = match base.get() {
        Some(b) => Url::parse(b).ok(),
        None => None,
    };
    match urlpattern::UrlPatternInit::parse_constructor_string::<SmRegexp>(text, base_url) {
        Ok(init) => parse_from_init(init, ignore_case),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_parse_init(init: *const RyInit, ignore_case: bool) -> *mut c_void {
    parse_from_init(lib_init(&*init), ignore_case)
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_free(pattern: *mut c_void) {
    if !pattern.is_null() {
        drop(Box::from_raw(pattern as *mut Pattern));
    }
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_has_regexp_groups(pattern: *const c_void) -> bool {
    let p = &*(pattern as *const Pattern);
    p.has_regexp_groups()
}

/// 0 protocol .. 7 hash.
#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_component(pattern: *const c_void, index: u32) -> *const c_void {
    let p = &*(pattern as *const Pattern);
    let c: &Component = match index {
        0 => &p.protocol, 1 => &p.username, 2 => &p.password, 3 => &p.hostname,
        4 => &p.port, 5 => &p.pathname, 6 => &p.search, _ => &p.hash,
    };
    c as *const Component as *const c_void
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_component_pattern(component: *const c_void) -> RyStr {
    let c = &*(component as *const Component);
    RyStr::of(&c.pattern_string)
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_component_regexp_empty(component: *const c_void) -> bool {
    let c = &*(component as *const Component);
    match &c.regexp {
        Ok(regexp) => regexp.pattern_string() == "^$",
        Err(_) => false,
    }
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_component_group_count(component: *const c_void) -> usize {
    let c = &*(component as *const Component);
    c.group_name_list.len()
}

#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_component_group_name(component: *const c_void, index: usize) -> RyStr {
    let c = &*(component as *const Component);
    match c.group_name_list.get(index) {
        Some(name) => RyStr::of(name),
        None => RyStr::none(),
    }
}

// Firefox helpers.rs matcher_matches, adapted from rust-urlpattern matcher.rs.
fn matcher_matches(matcher: &Matcher, mut input: &str, match_only: bool) -> Option<Vec<Option<String>>> {
    let prefix_len = matcher.prefix.len();
    let suffix_len = matcher.suffix.len();
    let input_len = input.len();
    let ignore_case = matcher.ignore_case;
    if prefix_len + suffix_len > 0 {
        if input_len < prefix_len + suffix_len || !input.starts_with(&matcher.prefix)
            || !input.ends_with(&matcher.suffix) {
            return None;
        }
        input = &input[prefix_len..input_len - suffix_len];
    }
    match &matcher.inner {
        InnerMatcher::Literal { literal } => {
            if ignore_case {
                (input.to_lowercase() == literal.to_lowercase()).then(Vec::new)
            } else {
                (input == literal).then(Vec::new)
            }
        }
        InnerMatcher::SingleCapture { filter, allow_empty } => {
            if input.is_empty() && !allow_empty {
                return None;
            }
            if let Some(filter) = filter {
                if ignore_case {
                    if input.to_lowercase().contains(filter.to_lowercase().collect::<Vec<_>>().as_slice()) {
                        return None;
                    }
                } else if input.contains(*filter) {
                    return None;
                }
            }
            Some(vec![Some(input.to_string())])
        }
        InnerMatcher::RegExp { regexp, .. } => regexp_exec(regexp.as_ref().ok()?, input, match_only),
    }
}

/// Matches one component; each capture goes to the sink (invalid = undefined).
#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_component_matches(component: *const c_void, input: RyStr,
                                                            match_only: bool, sink: *mut c_void) -> bool {
    let c = &*(component as *const Component);
    let text = input.get().unwrap_or("");
    match matcher_matches(&c.matcher, text, match_only) {
        Some(items) => {
            if !match_only {
                for item in &items {
                    ruyijs_urlpattern_sink(sink, match item { Some(s) => RyStr::of(s), None => RyStr::none() });
                }
            }
            true
        }
        None => false,
    }
}

fn emit(sink: *mut c_void, input: urlpattern::UrlPatternMatchInput) -> bool {
    let Some(m) = quirks::parse_match_input(input) else { return false };
    for value in [&m.protocol, &m.username, &m.password, &m.hostname, &m.port, &m.pathname, &m.search, &m.hash] {
        unsafe { ruyijs_urlpattern_sink(sink, RyStr::of(value)) };
    }
    true
}

/// The eight processed match-input components of a URL string (and optional base).
#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_match_input_string(url: RyStr, base: RyStr, sink: *mut c_void) -> bool {
    let Some(text) = url.get() else { return false };
    match quirks::process_match_input(quirks::StringOrInit::String(Cow::Borrowed(text)), base.get()) {
        Ok(Some((input, _))) => emit(sink, input),
        _ => false,
    }
}

/// The eight processed match-input components of a URLPatternInit.
#[no_mangle]
pub unsafe extern "C" fn ruyijs_urlpattern_match_input_init(init: *const RyInit, sink: *mut c_void) -> bool {
    match quirks::process_match_input(quirks::StringOrInit::Init(quirks_init(&*init)), None) {
        Ok(Some((input, _))) => emit(sink, input),
        _ => false,
    }
}
