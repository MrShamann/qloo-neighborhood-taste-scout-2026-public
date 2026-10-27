# Neighborhood Taste Scout — Qloo Agentic Hackathon

**Independent MIT-licensed source. Public fictional preview is online; authenticated Qloo verification and final Devpost submission remain pending.**

[Interactive Cloudflare Free demo (FICTIONAL data only)](https://qloo-neighborhood-evidence-agent.jy-edward.workers.dev/) · [Static backup preview](https://mrshamann.github.io/qloo-neighborhood-taste-scout-2026-public/)

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

The Qloo hackathon team confirmed on October 26 that authenticated event requests are free through judging, without automatic paid charges, and the judge app must return **live results** (not historical cached responses). A strictly bounded local genuine Qloo proof completed two Search GETs and one Insights GET on October 27: **3/3 authenticated calls, three live venue entities, explicit attribution for both inputs on all three**. The original source/trace is kept privately and excluded from GitHub. No venue opening hours, group fit or measured impact is claimed.

## Cloudflare Workers Free — live judge runtime

This standalone app uses a personally controlled Workers Free account plus one SQLite Durable Object. Each judge request runs a fresh 3-GET workflow, never reuses a prior Qloo response, and never saves raw Qloo data in Durable Objects, Workers KV, a source repository or a static asset. Only total reserved API call budget and a short-lived in-flight lease are persisted. Each run is serialized and fails closed on a busy request, unauthorized source, invalid schema or exhausted fixed budget. There are no automatic provider retries and no payment, booking, personal profiles or paid infrastructure.

The event credential is installed exclusively as a Cloudflare encrypted Worker secret, never exposed to the browser, a Git commit or a demo screenshot.

Build synthetic static assets in an isolated worktree:

```sh
python3 -B cloudflare/build_public_assets.py
```

The generated `cloudflare/public/` directory is excluded from source control. Inspect the generated assets and account plan before any deployment. Testing with `wrangler dev --local` is local-only and makes no approved public release. **Do not configure a Qloo key or deploy to a paid plan without exact authorization.**

## Evidence and limitations

Original code passed 117 Python tests and its latest Worker test suite; desktop and mobile browser tests include forged-zero-source and stale-scene rejection. Synthetic test fixtures are clearly labeled. One real Qloo 3-GET local proof completed October 27; no source API credential, private live result cache, individual profile, user benefit, finalist status or prize is claimed.

Source code and synthetic fixtures are MIT licensed. Qloo live result data remain subject to Qloo terms; the public source carries no license grant to Qloo content. The actual publicly accessible app must pass its own anonymous judge validation before a final Devpost submission can be claimed.
