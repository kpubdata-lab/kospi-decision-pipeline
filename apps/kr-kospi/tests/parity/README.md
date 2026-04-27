# v0.2 parity snapshots

These parity snapshots freeze the current v0.2 connector normalization contract before v0.3 connector work lands. Each file under `../fixtures/parity/v0.2/` stores both the recorded raw source payload and the normalized `ConnectorRow` output that the current connector implementation produces from that payload.

## Why these snapshots exist

- protect the v0.2 ECOS/KRX/KOSIS normalization shape during the v0.3 migration
- give default pytest coverage a deterministic regression net without live API calls
- make intentional connector behavior changes explicit in review by updating a golden snapshot

## When to regenerate

Regenerate a snapshot only when a connector's intended normalized behavior changes. Pure refactors that preserve output should keep these files unchanged.

## How to regenerate

1. Choose the same golden windows captured here:
   - ECOS `base_rate`, `usd_krw`, `bond_yield_3y`: `2024-01-01` → `2024-01-31`
   - KRX `kospi_index`, `investor_flow`, `market_valuation`: `2024-01-02` → `2024-01-08` (5 trading days)
   - KOSIS `industrial_production`: `2024-01-01` → `2024-03-31`
2. Record the live raw payload in the same JSON shape already used by the connector fixture tests.
3. Feed that recorded raw payload back through the live v0.2 connector implementation with fixed clock/API-key test doubles so the normalized rows are deterministic.
4. Replace the snapshot file with a JSON object shaped as `{"window": ..., "raw": ..., "normalized": ...}`.
5. Re-run `apps/kr-kospi/tests/parity/test_v02_baseline.py` and the full verification suite before opening the PR.

Do not regenerate snapshots during normal test runs or CI; they are checked-in golden fixtures.
