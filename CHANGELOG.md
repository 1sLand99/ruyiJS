# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.4] - 2026-10-26

### Fixed

- `python -m ruyijs.examples <name>` failed with "示例文件不存在" from an installed
  wheel: the example locator used a sentinel file (`turnstile/turnstile.py`) that is
  not shipped, so it never recognized the installed layout and looked in the wrong
  directory. It now uses `google/google_search.py`, which ships. Affected every
  example when run from the installed package.

### Removed

- `datadome` and `turnstile` entries from the examples CLI registry; their files are
  not distributed, so they could never run.

## [0.1.2] - 2026-10-22

### Added

- Examples ship inside the wheel as `ruyijs.examples`; run `python -m ruyijs.examples` to list them.
  DataDome offline replay captures are not included.

### Changed

- Bundled runtime rebuilt from the current sources (`js.exe` SHA-256 `0b827e48…`).

## [0.1.1] - 2026-10-22

### Added

- `Context.navigate(url)`: a browser-initiated top-level navigation (no Referer, `Sec-Fetch-Site: none`).

### Changed

- Bundled runtime rebuilt from the current SpiderMonkey shell (`js.exe` SHA-256 `c1e89f22…`), including
  the parser and event fixes made after 0.1.0.
- Published on PyPI as a Windows x64 wheel: `python -m pip install ruyijs`.

## [0.1.0] - 2026-10-21

### Added

- Installable Windows x64 Python wheel with a bundled, SHA256-pinned runtime.
- Source installation through Gitee, version metadata and `get_runtime_path()`.
- Installed-package examples and Python 3.10 / 3.14 integration verification.

- First public release of ruyijs: a SpiderMonkey (Firefox 158) runtime for Windows x64 with a
  Python binding, the `ruyijs_client.dll` C ABI and a CLI.
- A native browser environment across 38 bounded contexts, with a validated fingerprint/profile
  configuration.
- Page loading with iframes, a deterministic clock and event loop, trusted input, and console and API logs.
- The Necko network transport (HTTP/1.1, HTTP/2, HTTP/3) with per-context proxies.
- A portable release export with embedded Python, licenses, a source archive and checksums.
