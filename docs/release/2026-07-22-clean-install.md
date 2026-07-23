# 0.1.0 Clean-Install and Artifact Verification

Date: 2026-07-22
Status: release-candidate gate passed; publication not executed
Reference platform: macOS arm64

## Final candidate artifacts

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `llm_memory_store-0.1.0-py3-none-any.whl` | 74,771 | `8cfacde2bf043241517c196a1d97a842e49094e3fbf3adda67a3703246b8cb85` |
| `llm_memory_store-0.1.0.tar.gz` | 70,412 | `a9ddeb89c8c4c628127225edf4ec2c7471efa20b2f87ced04f9ceb89a8185887` |
| `0.1.0-sbom.cdx.json` | 67,250 | `a33f6734e964f3c3f133efebf0a07e8fad53a6d07ee5f7f251fcb8ea6f32adf1` |

The wheel contains only the Python package, entry-point/metadata records, and Apache-2.0 license. The
source distribution contains 21 members: package source, build metadata, README, changelog, license,
and contribution/security/support policies. It excludes tests, evaluations, demos, dashboards,
architecture reviews, generated dependencies, build outputs, and local artifacts.

PEP 639 metadata records `Apache-2.0` and the included license file. Five canonical Codeberg project
URLs are present. Twine 6.2.0 validates both Python artifacts.

## Wheel lifecycle matrix

The wheel was installed into a fresh virtual environment for each interpreter. Installation resolved
dependencies from the configured package index. The lifecycle itself set Hugging Face/Transformers
offline controls and used `DeterministicEmbedder`; it performed no model or network access.

| Python | Result |
| --- | --- |
| CPython 3.11.15 | Pass |
| CPython 3.12.11 | Pass |
| CPython 3.13.3 | Pass |
| CPython 3.14.5 | Pass |

Each run imported version 0.1.0 from the installed wheel and exercised commit, semantic recall,
provenance-linked typed memory, correction, JSON export, SQLite backup, previewed verified hard
deletion, integrity/orphan checks, restore into a new database, and post-restore recall using only
synthetic content.

## Dependency and security evidence

- `uv.lock` records Python dependency versions and source-artifact hashes.
- `package-lock.json` records the dashboard dependency graph and integrity values.
- pip-audit 2.10.1 found no known vulnerability in the locked production dependency export.
- CycloneDX 1.6 SBOM generation used cyclonedx-bom 7.3.0 against a Python 3.13.3 environment synced
  to the locked production set, followed by a no-dependency install of the candidate wheel.
- The SBOM contains 50 components, three direct root dependencies, and 108 dependency edges.
- Gitleaks 8.30.1 reports zero unresolved findings for full history and the prospective publication
  tree. Candidate artifacts receive the same archive-aware scan before handoff.

## Quality gates

- Python: 127 tests passed.
- Ruff: passed.
- Dashboard ESLint: passed.
- Dashboard build and rendered HTML test: passed.
- `git diff --check`: passed.

## Remaining external actions

The canonical source repository is `https://codeberg.org/manojpardeshi/agent-memory-store`, seeded
from the reviewed tree as one clean root commit with a Codeberg noreply identity. No tag, Codeberg
release, PyPI project, or package upload is created by this evidence run. The reproducible gate and
token-minimizing interactive publication sequence are documented in `docs/release/publishing.md`;
the remaining blocker is the PyPI account credential step.
