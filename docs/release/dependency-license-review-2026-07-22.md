# Dependency License Review

Date: 2026-07-22
Updated: 2026-07-23 after the dashboard security refresh
Decision: Apache-2.0 is compatible with the reviewed dependency set

This is an engineering inventory, not legal advice. Exact dependency versions and downloadable
artifact hashes are recorded in `uv.lock` and `demo/dashboard/package-lock.json`.

## Python runtime closure

The locked environment contains 47 runtime distributions reachable from `fastembed`, `mcp`, and
`sqlite-vec`. Installed package metadata and shipped license files identify MIT, Apache-2.0, BSD,
MPL-2.0, PSF-2.0, 0BSD, Zlib, CC0-1.0, MIT-CMU, or compatible multi-license expressions.

`py_rust_stemmers` 0.1.8 omits a license expression from its package metadata, but its installed
distribution includes an MIT license file. `fastembed` includes Apache-2.0 and its own NOTICE;
`mcp` includes MIT; `sqlite-vec` declares MIT and Apache-2.0. These dependencies are installed as
separate distributions and are not vendored into the project wheel.

No reviewed Python runtime dependency requires the project source to adopt a copyleft license.

## Dashboard closure

The dashboard lock contains 626 dependency package entries with no missing license metadata. The recorded
expressions include MIT, Apache-2.0, BSD, ISC, MPL-2.0, LGPL-3.0-or-later, CC-BY-4.0, CC0-1.0,
BlueOak-1.0.0, Python-2.0, and multi-license combinations.

Dashboard dependencies are not included in the Python wheel, and generated `node_modules` and build
outputs are excluded from source distributions. A separately distributed compiled dashboard would
require its own notice/source-offer review, particularly for LGPL and attribution-licensed inputs.

The 2026-07-23 refresh updated Next.js, React, the Cloudflare Vite plugin, Wrangler, Vite, and safe
transitive resolutions, with an explicit Sharp override to the patched 0.35 line. The resulting
locked graph reports zero npm audit vulnerabilities and still passes lint, build, and rendered-HTML
tests.

## Project license

Apache-2.0 was selected over MIT because both preserve permissive use while Apache-2.0 adds an
explicit patent grant and patent-termination terms. Contributions are accepted under Apache-2.0
section 5 without a separate contributor license agreement.

The dependency inventory must be regenerated whenever either lockfile changes and before each public
release. Release artifacts are scanned separately; this review does not authorize vendoring or
redistributing third-party source beyond its license terms.
