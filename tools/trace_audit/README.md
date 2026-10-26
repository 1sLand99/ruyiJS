# Trace audit and replay evidence

These offline tools inspect the native Firefox JSCT/JSCV v1 capture and exercise
the existing ruyijs production runtime. They install no browser APIs. Each Python
module stays below 200 lines: binary format reading, JSONL scanning, HTTP bodies,
causal joins, supplementary evidence, measurements and replay orchestration have
separate responsibilities. Call IDs are process scoped; a resolved parent remains
the nearest recorded ancestor, potentially separated by unobserved JIT frames.

From the ruyijs root, in PowerShell:

```powershell
$capture = 'D:\firefox\src\firefox\dom\bindings\domtrace\runs\jscall-detail-desktop-20261024-023506'
python -B -m tools.trace_audit $capture --output artifacts/trace-audit-20261024-023506/report.json
python -B -m tools.trace_audit.extras $capture --output artifacts/trace-audit-20261024-023506
python -B -m tools.trace_audit.benchmark --output artifacts/trace-benchmark-new --rounds 3
python -B -m tools.trace_audit.replay_probe $capture --output artifacts/trace-replay-new --advance-ms 5000
python -B -m tools.trace_audit.chain_index $capture --output artifacts/trace-audit-new/calls.sqlite
python -B -m tools.trace_audit.chain $capture --index artifacts/trace-audit-new/calls.sqlite --output artifacts/trace-audit-new/http-ancestry.json
python -B -m tools.trace_audit.interval_probe --output artifacts/interval-trace-new
python -B -m tools.trace_audit.random_state $capture/domtrace/trace_process_34928.jsonl --deps artifacts/random-replay-20261024/deps --output artifacts/random-new/inferred-state.json
python -B -m tools.trace_audit.crypto_inputs $capture --output artifacts/crypto-new/inputs.json
python -B -m unittest discover -s tests -p test_trace_audit.py -v
```

Benchmark/replay output directories must be new. The auditor reads JSONL in a
stream and retains compact sorted call IDs for joins, without decoding argument
payloads. It reports corruption, truncated values, unresolved references, missing
metadata and observed writer counters separately. No report field asserts full
execution coverage. Body hashes verify the stored representation; text hashes
do not prove original HTTP wire bytes.

The benchmark uses fresh Firefox profiles and a loopback page, permutes the
three modes in each round and retains every sample plus executable/source hashes.
It compares a small descriptor/toString/Proxy-getter observation and an explicit
microtask/timer/event chain. It does not prove general indistinguishability or
site-level overhead. Millions of optimized JS calls can produce only a few
records; always assess overhead alongside coverage. The separate Firefox tool
`tools/domtrace_switch_performance_compare.py` measures persistence modes and
provides a broader throughput/heartbeat baseline.

The SQLite index stores unsigned call IDs as eight-byte keys, preserving their
full range, and hashes input call/dictionary files. HTTP ancestry queries verify
those inputs and process nonces before following recorded parents. A path ending
at an observed root does not prove a complete direct-call stack. Truncation,
missing parents, cycles and limits are explicit. A partially built index stays
marked incomplete and is rejected. The causal audit keys local async IDs by
run/process instance/session. Message IDs already encode sender nonce and span
process-local trace_run_id values, so they are matched across process namespaces;
duplicate or missing message IDs never select an arbitrary sender.

`random_state` optionally uses z3-solver (this experiment installed version
5.3.1.0 only in its artifact deps directory) to solve the low-53-bit outputs of
SpiderMonkey xorshift128+. It separates training, held-out output validation,
alternative-model checking, and bounded forward-gap searches. All states are
inferred under a contiguous same-realm assumption; timeout is not uniqueness.
`script_order` reads an HTML packet and script_root/readyState evidence to emit
an explicit interactive-boundary order for async classic scripts. Replay accepts
`--random-state` and `--script-order` to exercise these inputs through the native
runtime. No other realm state or full event schedule is implied. Per-request
candidate and body-hash comparisons expose the next divergence.

`crypto_inputs` selects a random call only when active script_root URL, stack
URL, a unique captured document and one Crypto receiver identity agree. It
accepts complete getRandomValues postArgs and valid randomUUID output, retaining
source hashes, call IDs and rejection evidence. External-script/ambiguous roots
are rejected rather than attributed to the nearest convenient document. The
replay's `--crypto-inputs` option routes exact document occurrences to their
original native Crypto instance. Operation, length, exhaustion and consumption
are checked; status reports counts without bytes. `request_diff` reports body
length, stored hash and common-prefix evidence without claiming encrypted-body
semantic similarity. `boundary_diff` compares primitive host values at matching
source coordinates only when occurrence counts agree; object encodings and
ambiguous occurrences are excluded.

`value_coverage DETAIL --call-id ID --output FILE` identifies exactly which value
representations exist at selected calls. Object class labels are explicitly
marked as lacking property snapshots even when truncation flags are clear.
`random_state --check-contiguous` tests the hypothesis that all observed outputs
are consecutive in one realm; unsat rejects that hypothesis without applying a
seed or claiming a specific missing-call count.

`object_snapshot_probe --output NEW_DIRECTORY` verifies the opt-in Firefox
JSCV type-15 serializer through real local browser processes. It compares off,
detail, selected object snapshots, call budget, byte budget, core-off independent
logging and excluded names. Run `verify_object_snapshots REPORT` to require
actual capture, typed omissions, data fields, return values, unchanged page
results and zero getter/Proxy/toJSON side effects. `--benchmark` retains raw
timings and coverage counts; small timings or sparse JIT-visible records do not
prove zero overhead. The optional format and capture switches are documented in
Firefox `dom/bindings/domtrace/OBJECT_SNAPSHOT_20261024.md`.

The replay probe copies the selected shell and DLLs to its artifact directory,
omits `vendor/necko-derived/python/python.exe`, and registers captured GET
resources through `Context.put_resource`. The existing Necko transport therefore
has no executable helper for unmatched HTTP requests. No original Firefox profile
or live credentials are used. This is a bounded divergence experiment: the
resource owner matches by URL (with its existing query fallback), not by request
method/body/occurrence. It retains the first GET response and reports conflicting
later responses. It does not replay input, RNG, all clocks, POST responses or the
recorded task schedule; it never reports deterministic replay as verified.

The target audit and next implementation requirements are recorded in
[the analysis](../../docs/TRACE_REPLAY_20261024.md). Captures and executables stay
under ignored `artifacts/`; they are not source deliverables.

`navigation_inputs RUN --process-id PID --output FILE` extracts a process prefix
before its first XHR send, grouping actual PerformanceNavigationTiming receivers.
A single document packet, a same-URL script root, stable name, entry type and
getter stack are required. Conflicting observations are rejected. Missing fields
stay absent; a positive stable navigation duration derives loadEventEnd explicitly.
`replay_probe --navigation-inputs FILE` passes these fields through the native
Scheduling owner, with exact URL/occurrence binding and original load completion.
This neither moves the replay clock nor substitutes responses for different POSTs.

`navigation_observer_probe --output NEW_DIRECTORY --require-parity` compares the
actual local Firefox main/frame observer lifecycle, native identity, buffered
queries and filters to ruyijs. `navigation_replay_evidence` joins this oracle,
the bounded extraction, disabled-input ablation, traced/untraced outputs and
final build/tests. A smaller encrypted request or longer common prefix is not
treated as a monotonic correctness metric.

`payload_alignment CAPTURE REPLAY --pid PID --array-call ID --serializer-call ID
--output NEW_DIRECTORY` verifies a complete JSCV byte array, its raw-DEFLATE
roundtrip, sibling serializer offset and unique HTTP encoder-return match. A
complete matching serializer subtree in standalone jscall is reconstructed only
when all scalar values, container pairs and byte offsets are present. Later trace
budget exhaustion is reported separately. The tool emits local decoded JSON and
structural differences; it does not replace page state or outgoing requests.

`payload_origins CAPTURE ALIGNMENT --output FILE` verifies the reviewed fourteen
numeric source mappings for deployment 20261024-023506. Its process/line/field
mapping is deliberately deployment-specific, not a generic taint analysis. Actual
message fields and Date.now observations remain linked to source hashes.

`capture_cost --output NEW_DIRECTORY` runs a fixed loopback workload in off/core/
calls/detail modes, randomizing order within each of three rounds. Each run uses
a new profile and records wall time, process-tree CPU, sampled working sets,
checksums, surface probes, trace bytes and actual leaf/bytes call coverage.
Requires psutil; all monitoring runs outside the page. `cost_summary REPORT`
rejects incomplete pairs, empty captures, writer/binary discrepancies and changed
behavior. `capture_cost_report REPORT --output DIRECTORY` writes standalone
Markdown/CSV plus an evidence manifest. Ratios do not establish zero overhead,
especially with sparse JIT call coverage; samples retain those qualifications.

`tier_probe --output NEW_DIRECTORY` runs a loopback-only factorial study: normal
tiers and explicit interpreter diagnosis, each with off/calls/detail. Browser
preferences are read back before executing the unchanged fixture; this does not
modify default product preferences. `tier_summary REPORT` validates complete
cells, checksums, known invocation counts and actual writer/byte records. Run
`tier_report REPORT --output DIRECTORY --plot-deps LOCAL_DEPENDENCIES --verify-binaries`
to rescan raw captures and export Markdown, CSV, PNG, PDF and SVG with source hashes.
The graph separates execution-tier policy cost from tracing cost and coverage.
No opcode instrumentation is implemented or measured by this experiment.

`tier_integrity REPORT --output NEW_DIRECTORY` reuses the preserved local tier
fixture data and original file hashes. It checks parent/thread/depth/leave order,
matches binary call records to nested values, validates each recorded numeric
result against an independent integer oracle, and reconstructs checksums only
for complete fixture sequences. Object labels remain explicitly incomplete.
`local_trace_replay PROOF --output NEW_DIRECTORY` uses the recovered bounded
inputs in the unchanged local source through Python and the real C DLL. This
proves only the fixed synchronous fixture; it is not whole-page/task replay.
`tier_integrity_report` publishes counts, scope and a hash-indexed local report.

`async_probe --output NEW_DIRECTORY` runs a loopback-only fifteen-step chain using
microtasks, Promise, timeout, synchronous EventTarget, window/port/frame/Worker
messages and an interval. `verify_async_probe REPORT --output FILE --require-contexts`
requires explicit context declarations, exact schedule/message joins and real
binary call IDs. No timestamp-nearest or file-adjacency inference is used.
`async_edges_probe` covers DOM get/set/static calls, nested callbacks and trace
gate reopening. `async_runtime_probe` verifies behavior in Python/C; it does not
consume or replay the browser task graph. `async_report` joins the final evidence.

`concurrent_probe --output NEW_DIRECTORY` presents three loopback-backed sites
to real Fission processes and sends equal-payload messages through two frame/
Worker branches. `concurrent_verify REPORT --output FILE` joins 16 four-hop
circuits per capture using process/session context IDs and message tokens.
`message_graph` never uses wall time or payload text to select a sender. Calls
that map only to an outer recorded frame are explicitly classified as observed
ancestors. `concurrent_report` revalidates source hashes, JSON proof persistence
and every file-merge permutation, then publishes the partial-order result.

`evidence_audit --output NEW_DIRECTORY` reads the preserved 20261024 manifests
and verifies explicitly declared file identities using their actual path bases.
It reports historical build, working source and document drift separately from
missing or changed evidence. A copied tier summary explicitly points to its
`final-report` output directory. No historical digest is rewritten. Matching
hashes establish consistency with the manifest, not semantic correctness or
authorship. Embedded paths and historical pass flags are not recursively treated
as authenticated evidence. It uses only the Python standard library and does
not launch a browser or send network requests. See
`docs/EVIDENCE_AUDIT_DESIGN_20261024.md` for ownership and scope.

`async_contract_run CAPTURE_REPORT --output NEW_DIRECTORY` compiles the preserved
serial local fixture into explicit marker groups, then consumes those groups at
one-task host RPC boundaries through Python/C. Deliberately changed expectations
must fail. This checks observable checkpoints; it does not select ready tasks by
recorded identity or control Worker execution. `async_mapping_probe --output
NEW_DIRECTORY` measures same-caller timer registration ambiguity and deferred
Promise provenance in off/core/calls Firefox captures. `async_consumption_report
EXPERIMENT_DIRECTORY` revalidates stored mapping evidence and publishes the
bounded result. See `docs/ASYNC_CONSUMPTION_DESIGN_20261024.md`.

`timer_identity_probe --output NEW_DIRECTORY` checks optional native Window
timer register/fire/finish/cancel/clear-all identities, receiving-global handle
isolation, interval cancellation, string callback, frame removal, gate and cap.
`timer_lifecycle.prove_timers` joins explicit async/global/public-handle/native
IDs and fails on gaps or ambiguous DOM registrations. `timer_identity_cost
--output NEW_DIRECTORY` measures off/core/timers in three randomized rounds,
checking actual register/cancel coverage. These commands need the experimental
Firefox build implementing MOZ_DOM_TRACE_TIMERS; Worker timer coverage and
record-driven task selection remain outside this slice.

`selected_timer_replay TIMER_IDENTITY_DIRECTORY --output NEW_DIRECTORY` compiles
the saved local sibling-timer lifecycle evidence into host commands. It uses
the opt-in native configure_timer_replay/pending_timers/run_timer RPCs through
Python and the real C DLL. Each recorded public handle maps to an existing live
task; the owner validates firing count and readiness before selecting it. Two
counterfactual reorder controls demonstrate actual execution control. The
adapter is restricted to the exact fixed single-main-realm fixture, uses owner
deadlines, and does not replay the original webpage or Worker/message schedule.
`timer_selection_report EXPERIMENT_DIRECTORY` revalidates saved plans and
publishes the bounded result with source/build identities.

`frame_timer_replay TIMER_IDENTITY_DIRECTORY --output NEW_DIRECTORY` consumes
the saved multi-frame timer fixture using explicit timer_realm host queries.
The exact source's recorded registration sites map capture globals to frame
roles; runtime realm IDs may differ. Normal/reversed prebinding and deliberately
exchanged-frame controls test mapping, repeated handle=1, interval occurrences,
string-handler script-root ancestry and removed-frame cancellation. This is a
fixed-source same-origin adapter, not general DOM/WindowProxy reconstruction.
`frame_timer_report EXPERIMENT_DIRECTORY` revalidates its published plan/results.

`message_selection_report EXPERIMENT_DIRECTORY` publishes the opt-in same-process
WindowMessaging identity-selection result. The message task carries source and
target installed-global realm positions, a source sequence, kind and its existing
Scheduling task ID. `pending_messages`/`run_message` validate all fields before
the original MessageEvent trampoline runs. Dedicated Worker and cross-process
relay remain outside this interface; equal payloads and wall-clock order are not
identity keys.
