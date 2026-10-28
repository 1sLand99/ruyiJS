# Original CompressionStream dependencies

Frozen copies of Firefox's libz-rs-sys 0.6.3, zlib-rs 0.6.3, Brotli revision
4792c8e4c4235f6b501f13dbd07a8b4b253eee21 and original zlib C ABI headers.
`manifest.json` identifies every upstream file with source path and SHA-256.
Upstream source files and licenses are unchanged.

`tools/compression_native.py` compiles these sources offline. The Rust C ABI uses
the upstream custom-prefix feature with RUYIJS_CS_Z_. The Brotli source inventory
comes from its frozen moz.build, compiled with BROTLI_BUILD_PORTABLE and dynamic
MSVC CRT. No Cargo registry, external package resolution, runtime sidecar, or
mutable full-Firefox objects are used. The build report records source hashes,
tool versions, commands, target and output hashes.

The Rust compiler is the exact donor config.status.json RUSTC path, so the codec
and donor jsrust static library use one compatible standard runtime archive.
Selecting an unrelated PATH compiler would link two std builds and collide on
unmangled runtime symbols. No duplicate-symbol suppression or symbol deletion is
used; the allocator, CPU detection and codec feature set remain donor-equivalent.
Both codec crates compile as rlibs and the librarian combines their code into a
native archive. Unlike staticlib, this does not generate another global allocator
shim or bundle another std runtime. The existing donor jsrust archive supplies
those once, including its original mozglue allocation policy.
