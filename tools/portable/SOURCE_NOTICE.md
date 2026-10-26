# Source and third-party notice

This Windows x64 package contains the existing ruyijs / SpiderMonkey runtime,
its Python binding and C ABI, and embedded CPython / Necko network dependencies.

source.zip contains current production source, Python, selected build/release tools,
Google examples, transport code, documentation, generated shell units and directly rebuilt donor
shell sources. SOURCE_MANIFEST.json records the archived files and their hashes.
provenance/build-runtime.json is the original historical build record; it is not
a new validation of all current source files. Tests, diagnostics, captured pages
and temporary outputs are excluded from this distribution.

The source archive contains project and derived sources, not the complete Firefox
tree. Rebuilding requires the matching standalone
Firefox donor, static objects, compiler and Windows SDK identified in the original
build record. Distribution of this subset does not certify a fresh full regression.
The build tools and source notices describe the external donor requirements;
the local build paths in provenance are records, not portable runtime dependencies.

Mozilla terms and component notices are preserved in licenses/mozilla/LICENSE
and licenses/mozilla/toolkit/content/license.html. The donor shell sources retain
their MPL notices. CPython, Necko and other network component licenses are preserved
under licenses/necko-derived and within the embedded runtime's package metadata.
HarfBuzz's original COPYING notice is preserved under licenses/harfbuzz.
Rust encoding component terms are preserved in source.zip under
ruyijs/src/web_platform/encoding_rs/LICENSE-APACHE and LICENSE-MIT.

The MSVC runtime DLLs retain their original Microsoft terms. No new license is
assigned here to project files without an explicit license, nor are rights to
Mozilla names or logos granted by including source files.

The inherited Necko manifests describe the original dependency bundle. The
build-runtime.json networkHelper record identifies the production oneshot.py
replacement; SHA256SUMS records the actual files shipped after test/cache removal.
evidence/necko-release-files.json records the cleaned development dependency tree;
it includes provenance and wheelhouse files that are not runtime package members.
Use SHA256SUMS for the exact portable layout. The current base and native source
inventories are included in source.zip for re-derivation provenance.

evidence/portable-verification.json records only the actual portable smoke checks
of this package. It is not a claim of complete browser compatibility or a fresh
full-source regression. SHA256SUMS covers every package file except itself.
