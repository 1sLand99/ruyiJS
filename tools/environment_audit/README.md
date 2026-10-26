# Firefox / ruyijs environment audit

Run from the repository root on Windows. Firefox uses a disposable headless
profile; behavior probes run as ordinary page scripts on a local HTTP fixture.
ruyijs receives that Firefox instance's navigator, screen, viewport and locale
profile. The collector installs no replacement browser APIs.

```powershell
python -u -B tools/firefox_parity/collect.py --output artifacts/AUDIT/surface
python -u -B tools/environment_audit/collect.py --output artifacts/AUDIT/page-behavior
python -B tools/environment_audit/report.py artifacts/AUDIT
```

Output directories must be new and under `artifacts`. `--probes dom network`
selects a smaller behavior set; `--firefox PATH` selects the reference binary.
Surface collection is HTTP and trusted localhost, main window and iframe.
Behavior collection is trusted localhost, main window and iframe; the Worker
probe also captures its own surface and behavior. Metadata identifies binary
and probe hashes and the effective environment.

Read `REPORT.md` for counts, `comparison.json` for exact behavioral differences
and `surface-findings.json` for observed interface differences. Surface counts
are observations, not independent defect counts. Owner labels are triage hints;
read the relevant owner record before editing production code.

The 2026-10-25 `page-behavior` run supersedes `behavior` and `extended`: the
earlier collector used host evaluation and gave misleading cross-origin results.
Always run security probes through ordinary script elements. Capture failures
are distinct from successfully captured but different API results. A zero
difference count proves only the fixed inputs exercised by that probe.

Current verified differences and unresolved areas are recorded in
`artifacts/environment-audit-20261025/TRIAGE.md`. Target login is a separate
acceptance test and is never inferred from environment parity counts.
