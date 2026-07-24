# 0.1.0 Publication Record

Date: 2026-07-24
Status: published and verified

## Public locations

- PyPI: `https://pypi.org/project/llm-memory-store/0.1.0/`
- Codeberg release: `https://codeberg.org/manojpardeshi/agent-memory-store/releases/tag/v0.1.0`
- Canonical tag: `v0.1.0`
- Release commit: `bd06701016e75832a5d17534352fd0e648fd8571`

## Published artifacts

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `llm_memory_store-0.1.0-py3-none-any.whl` | 74,917 | `2017d75edb9dc939b2f3c1c1c047e1148c904e106f52fcc867190a7c9f32b300` |
| `llm_memory_store-0.1.0.tar.gz` | 70,766 | `2efebd0b141fbf11fc93fb738b63bd14cadffc0cbee6067176eccd1c30cd8864` |
| `0.1.0-sbom.cdx.json` | 67,250 | `a33f6734e964f3c3f133efebf0a07e8fad53a6d07ee5f7f251fcb8ea6f32adf1` |

PyPI's version JSON reported the expected wheel and source-distribution hashes. The public Codeberg
release API reported a non-draft, non-prerelease release with the wheel, source distribution,
`SHA256SUMS`, and CycloneDX SBOM attached at the expected byte sizes.

## Post-publication verification

- A clean CPython 3.11.15 virtual environment installed `llm-memory-store==0.1.0` from PyPI.
- Installed metadata reported version `0.1.0`.
- Both `llm-memory --help` and `llm-memory-mcp --help` completed successfully.
- The temporary account-wide PyPI bootstrap token was revoked.
- The remaining `agent-memory-store-publishing` token is scoped only to `llm-memory-store` and is
  stored in macOS Keychain, not in the repository or CI.
- The tagged checkout rebuilt byte-identical Python artifacts with
  `SOURCE_DATE_EPOCH=1784764800`.

The pre-publication gate evidence remains in `docs/release/0.1.0-candidate-manifest.json` and
`docs/release/2026-07-22-clean-install.md`.
