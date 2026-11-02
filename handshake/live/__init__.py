"""The live integration plane.

Everything under `handshake/` outside this package measures the mechanism
against a simulated merchant, in-process. This package is what a real shop
plugs into: it ingests the HTTP traffic between AI shopping agents and a
merchant's checkout, works out why a journey stopped, gates any response
through the same eleven rules, and hands the merchant a directive it can apply.

    store.py       SQLite persistence, tenant-scoped: merchants, journeys,
                   events, catalogue, ledger, webhook deliveries, re-offers
    events.py      the normalised event schema and PII redaction
    detectors.py   why a journey stopped: ranked, evidence-backed hypotheses
    directives.py  what a permitted intervention asks the merchant to do
    pipeline.py    ingest -> abandon -> diagnose -> gate -> direct -> attribute
    webhooks.py    signed outbound delivery with retry
    api.py         the /v1 HTTP surface
"""
