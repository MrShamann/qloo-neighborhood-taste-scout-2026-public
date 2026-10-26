# Neighborhood Taste Scout — Qloo Agentic Hackathon

**Independent MIT-licensed source. Live Qloo verification and final Devpost submission remain pending.**

This original clean-room cultural decision-evidence agent is for an independent event curator who wants to inspect how two public artist influences relate to candidate places in one city. It explicitly separates source-backed evidence from fictional examples. NEXT, HOLD and ABSTAIN refer to whether source contributions for two IDs are present; they are **not** an assertion of shared user preference or of a venue's safety, hours or availability.

## Run the original Python app locally

Requires Python 3.11+; the application uses the Python standard library.

```sh
python3 -m unittest discover -s tests -q
python3 -m src.webapp --port 8765
```

Visit http://127.0.0.1:8765/ . The local demo uses *invented venues and scores*, with source badges clearly marked **fictional**. It must not be presented as an authenticated Qloo result.

## Qloo Taste AI integration

The real adapter pins HTTPS egress to `hackathon.api.qloo.com`. It resolves two independently typed artist entities using two bounded Search GETs, then queries one combined Insights GET for place entities in a selected city. It never infers missing explainability, never sends personal location or listening histories, and never books or pays for anything.

An event-issued API credential must be stored server-side only. The live path is deliberately disabled until verified event quota, rate, key expiry, absolutely no paid overage, source output display rights and a separately scoped authorization are recorded. No authenticated Qloo request has yet been performed in this release candidate.

## Optional Cloudflare Workers deployment candidate

The optional `cloudflare/` adapter is a *private* deploy candidate using Workers Free and a SQLite Durable Object to reserve a global maximum of three Qloo GETs before sending any request. Repeat visitors read previously validated results, without fresh sponsor requests. A failed first attempt never auto-retries or refunds the reserved quota. Neither a Cloudflare account plan nor a source-data redistribution grant has been verified for public release.

Build synthetic static assets in an isolated worktree:

```sh
python3 -B cloudflare/build_public_assets.py
```

The generated `cloudflare/public/` directory is excluded from source control. Inspect the generated assets and account plan before any deployment. Testing with `wrangler dev --local` is local-only and makes no approved public release. **Do not configure a Qloo key or deploy to a paid plan without exact authorization.**

## Evidence and limitations

The reviewed private source at `9ddb88e9563ea9d24bac6c19ce8dcdaca976da3c` passed 116 Python tests and 5 synthetic Worker tests; desktop 1440px and mobile 390px browsers passed local fictional-case and source-status tests. A clean-clone Worker test failure was traced to an incorrect dependency on generated static assets. The tests now use explicit synthetic stubs and passed independently before assets were built. All data in these tests are artificial. No real Qloo authenticated access, public judge host, user benefit measurement, finalist status or award is claimed.

Source code and original synthetic fixtures are offered under the **MIT License** (see LICENSE). The license does not confer Qloo API/data rights. A public functional demo and contest submission require separately verified sponsor authorization, real-provider evidence, hosting approval, and Devpost acceptance.
