# Portable Capability Candidate (Original Code Only)

This contest prototype includes a small, original provider-neutral portability contract under `capability/portable-manifest.v1.json`. It describes a **read-only cultural-evidence audit**, its public input/output contract, failure modes, required Qloo API, privacy, side effects, test paths and independent MIT ownership.

**Not a transfer:** the manifest and the separately generated checksum receipt are candidate metadata. They do not assert compatibility with any private operating system, copy another project's source, transfer Qloo result data, grant rights over a vendor API, or authorize importing code. Actual transfer requires a new IP/license, target interface, security and provider review.

After tests and a clean Git commit, an authorized reviewer may generate a private, hash-only provenance packet outside this repository:

```sh
python3 tools/export_capability_candidate.py --output ../QLOO_HARVEST_CANDIDATE_PRIVATE.json
```

The exporter fails on a dirty worktree or an existing/inside-repo output. It emits no source-code bytes, keys, Qloo responses, private-platform metadata or user profiles. SHA-256 verifies exact input bytes but is **not** an organizer signature or proof of right to import.

The original MIT license applies to our code and synthetic fixtures only; Qloo output and service permissions are separate.
