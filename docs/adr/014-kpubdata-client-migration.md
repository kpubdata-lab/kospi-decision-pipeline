# ADR-014: Finalize the `kpubdata.Client` Live-Ingest Migration

## Status
Accepted

## Date
2026-04-28

## Context
`kospi-decision-pipeline` started its live-ingest path with bespoke connector utilities for HTTP transport, retry policy, and source-specific secret resolution. That was acceptable while the live surface was still emerging, but by the end of the v0.3 migration cycle the repository had already moved the real ECOS, KOSIS, and KRX connector implementations onto `kpubdata`.

Keeping the legacy `_http.py` and `_secrets.py` helpers after that migration would leave two parallel integration stories in the tree:

- the shipped connector path using `kpubdata.Client`
- dead legacy scaffolding suggesting that direct per-source HTTP and secret management still mattered

That split increases maintenance cost, muddies operator documentation, and weakens the intended architecture boundary.

This migration also aligns with the `younggeul` sister-package pattern documented in [younggeul ADR-007](https://github.com/kpubdata-lab/younggeul/blob/main/docs/adr/007-kpubdata-live-ingest.md): keep public-data provider quirks, auth, and dataset wiring in `kpubdata`, while application repositories stay focused on deterministic Bronze/Silver/Gold contracts and domain logic.

## Decision
For v0.3.0, `kospi-decision-pipeline` uses **`kpubdata.Client` as the single live-ingest client for all shipped live sources**.

1. **Single auth surface**
   - ECOS reads `KPUBDATA_BOK_API_KEY`.
   - KOSIS reads `KPUBDATA_KOSIS_API_KEY` when the optional bronze-only ingest path is used.
   - KRX is authless and does not require a repository secret.

2. **Single client-construction path**
   - `connectors.client_factory.build_client()` is the only supported place that constructs a live `kpubdata.Client`.
   - `connectors.registry.LiveConnectorRegistry` remains the central wiring layer that maps `get_connector()` to `build_client()` and the shipped ECOS/KOSIS/KRX connectors.

3. **Dependency consolidation**
   - The documented live-ingest dependency target for this release is `kpubdata[krx]>=0.5.0,<0.6.0`.
   - The `[krx]` extra is the release-line contract for the authless KRX provider surface used by v0.3.

4. **Legacy infrastructure removal**
   - Delete the bespoke HTTP helper module.
   - Delete the bespoke secrets helper module.
   - Delete tests that only existed to cover those removed modules.

## Consequences

### Positive
- One provider-integration story across ECOS, KOSIS, and KRX.
- One environment-variable naming convention for live auth (`KPUBDATA_*`).
- Less duplicated provider plumbing inside the application repository.
- KRX operation is clearer because the live path is explicitly authless.

### Negative
- Live-ingest behavior now depends even more directly on the `kpubdata` release line.
- Operators upgrading from v0.2 must rename environment variables and stop relying on removed CLI-era auth assumptions.

### Neutral
- `registry.py` stays in place because it is still the live wiring boundary for the CLI and contract tests.
- Fixture-backed ingest remains unchanged and continues to be the safe fallback for CI and local dry runs.

## Migration steps for v0.2 → v0.3 users

1. **Rename environment variables**

   ```bash
   export KPUBDATA_BOK_API_KEY="..."
   export KPUBDATA_KOSIS_API_KEY="..."   # optional bronze-only KOSIS path
   ```

   - KRX does **not** require an API key.
   - `KPUBDATA_KRX_INTEGRATION=1` is only an authless integration-test gate, not a credential.

2. **Stop looking for a live `--api-key` flag**
   - v0.3 live ingest is env-var-only.
   - `Client.from_env()` is the supported auth entry point.

3. **Upgrade the live-ingest dependency**

   ```bash
   pip install "kpubdata[krx]>=0.5.0,<0.6.0"
   ```

4. **Keep KOSIS expectations narrow**
   - The optional KOSIS live path remains bronze-only in v0.3.
   - Silver/Gold/runtime still depend on KRX + ECOS for the shipped path.

## Alternatives considered

### A. Keep the bespoke HTTP/secrets helpers around “just in case”
- **Pros:** no deletion risk; easier rollback to the old shape.
- **Cons:** misleading dead code, duplicate integration story, extra maintenance.

### B. Revert some providers back to per-source live clients
- **Pros:** less coupling to `kpubdata`.
- **Cons:** loses the sister-package pattern, recreates auth drift, and reintroduces provider-specific plumbing that the migration just removed.

### C. Finalize the unified client migration (selected)
- **Pros:** consistent auth surface, clearer operator story, less in-repo plumbing, matches the `younggeul` pattern.
- **Cons:** tighter dependency on `kpubdata` release discipline.

## Related
- `docs/adr/001-project-foundation.md`
- `README.md`
- `docs/operator.md`
- `apps/kr-kospi/src/kospi_decision_pipeline_app_kr_kospi/connectors/client_factory.py`
- `apps/kr-kospi/src/kospi_decision_pipeline_app_kr_kospi/connectors/registry.py`
- `younggeul` ADR-007: `kpubdata` live-ingest sister-package pattern
- No ADR-013 currently exists in this repository; ADR-014 records the final v0.3 migration cleanup directly.
