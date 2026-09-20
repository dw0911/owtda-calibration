# OW-TDA-CAL R1 — Formal H0/H1 Result Audit (2026-09-18)

## Verdict under the frozen A/B/C audit rule

- **A — scientific correctness:** no new execution-level blocker found from the delivered evidence. The formal plan sizes and sealed H0/H1 identities are internally coherent. The current top-level aggregation is **not suitable as the manuscript's main estimand** because it pools distinct cells/methods; re-aggregation is required, not rerunning the Monte Carlo.
- **B — trial identity/completeness:** **PASS at plan/seal level.** NULL has 70,000 data units / 140,000 feature rows / 280,000 evaluation rows; ALT has 12,800 / 25,600 / 51,200. Plan, certificate, RUN seal, PHASE seal, admission summaries and shard registry cross-bind consistently. H1's PHASE seal correctly has the H0 PHASE seal as parent.
- **C — independent recomputation:** **NOT CLOSED BY THIS DELIVERY.** The package contains hashes, sizes and summaries, but not the actual evaluation/feature JSONL ledgers (~3.38 GB total). Therefore row-level p/reject validation, uniqueness, H1 source-null binding and per-cell aggregation cannot be independently recomputed from this ZIP alone.

**Action:** preserve the current sealed H0/H1 runs. Do **not** rerun them now. Run the supplied streaming verifier against the four local ledger files. If it passes exact hashes, counts, uniqueness, p/reject formula and H1 source-null binding, accept these runs. If it fails, rerun only the affected phase.

## 1. Package identity

Input: `owtda_cal_r5_h0h1_delivery_20260918.zip`

SHA256: `95e27739482283794ad9b2760eecb2ca9ec5fee2378caa39fd6f0140a72d2d91`

The ZIP has 14 files: G4 certificate, H0/H1 admission objects, RUN/PHASE seals, registries, PLAN_SUMMARY, aggregation/validation summaries, git log and shard content hashes.

## 2. Seal and identity consistency

All four seal hashes independently reproduce using canonical JSON (`sort_keys`, compact separators) plus a trailing newline:

- H0 RUN seal: PASS
- H0 PHASE seal: PASS
- H1 RUN seal: PASS
- H1 PHASE seal: PASS

For both NULL and ALT, all of the following are equal to the corresponding PLAN_SUMMARY values:

- evaluation expected-index hash in plan / certificate / RUN seal / PHASE seal;
- data expected-index hash in plan / RUN seal / PHASE seal;
- feature expected-index hash in plan / RUN seal / PHASE seal;
- evaluation row counts;
- feature row counts;
- data-unit counts;
- evaluation-ledger hash between RUN and PHASE seals;
- feature-ledger hash between RUN and PHASE seals;
- RUN-seal reference from PHASE seal;
- shard commit / manifest / plan references between registry and RUN seal.

H1's `parent_phase_seal_hash` exactly equals the H0 phase seal hash.

### Formal counts

| Phase | Data units | Feature rows | Evaluation rows |
|---|---:|---:|---:|
| NULL/H0 | 70,000 | 140,000 | 280,000 |
| ALT/H1 | 12,800 | 25,600 | 51,200 |
| Total | 82,800 | 165,600 | 331,200 |

These are exactly the registered formal-scale counts.

## 3. Aggregate-summary consistency

The delivered summary is arithmetically self-consistent:

### H0

| Feature / method label | n | rejects | pooled rate | approximate Wilson 95% CI |
|---|---:|---:|---:|---:|
| BPI / M0 naive | 70,000 | 29,867 | 0.426671 | [0.4230, 0.4303] |
| BPI / M1 DMB | 70,000 | 3,205 | 0.045786 | [0.0443, 0.0474] |
| MOMENTS / M0 naive | 70,000 | 38,236 | 0.546229 | [0.5425, 0.5499] |
| MOMENTS / M1 DMB | 70,000 | 3,545 | 0.050643 | [0.0490, 0.0523] |

The four groups sum to 280,000 rows and 74,853 rejects, matching `validation_summary.json`; reported p/reject mismatches are zero.

These pooled numbers are **encouraging sanity checks**: naive permutation is strongly anti-conservative overall, while M1 DMB is close to nominal 0.05 overall. They do **not** prove per-cell calibration because the research question is explicitly about calibration boundaries across overlap/dependence/budget conditions.

### H1

| Scenario | pooled n | rejects | pooled rejection rate | approximate Wilson 95% CI |
|---|---:|---:|---:|---:|
| mean_shift | 25,600 | 14,807 | 0.578398 | [0.5723, 0.5844] |
| shape_change | 25,600 | 16,397 | 0.640508 | [0.6346, 0.6464] |

The two groups sum to 51,200 rows and 31,204 rejects, matching `validation_summary.json`; reported p/reject mismatches are zero.

**Do not call these two pooled rates the final H1 powers.** Each scenario pools BPI/MOMENTS × M0/M1 and several cells, while the frozen design requires power, corresponding H0 size, size-standardized power and localization to be reported at the registered cell/method/feature level. Rename the current quantity to e.g. `pooled_rejection_rate_by_scenario` if it is retained as a diagnostic.

## 4. One non-blocking metadata inconsistency

`h1_run/FORMAL_ADMISSION.json` has `requested_phase="H0"` and points to `G4_H0_CERTIFICATE.json`, although the produced phase is ALT.

This is a governance/metadata inconsistency, but the delivered evidence does **not** show a trial-identity error:

- the certificate already binds the ALT expected-evaluation hash;
- the H1 RUN seal binds the ALT expected data/feature/evaluation hashes;
- the H1 PHASE seal says `phase="ALT"`;
- the H1 PHASE seal's parent is the exact H0 PHASE seal.

Therefore this should be recorded with an append-only correction/explanation and fixed for future runs. It does not justify rerunning the current H1 by itself.

## 5. The real remaining hard gate: raw-ledger independent validation

The delivery references these local ledgers by SHA256 and size, but does not contain the bytes:

### H0
- evaluation: 1,404,096,576 bytes, SHA256 `744141035fdb5f651b19f3e7998cc4f7223356dcdc7eea1f92a2390e689391d8`
- feature: 1,437,310,000 bytes, SHA256 `16b854523097d258095a70e2ea2d0ad07669100e5ccb70caff336c4dfaf43a5f`

### H1
- evaluation: 266,379,930 bytes, SHA256 `82ddef2b75e303dedc9038cf29cc9dac26d1867e2c89fc951842c4b5967052c7`
- feature: 262,233,600 bytes, SHA256 `4ba3d1f7407719bec9e72d4b9d8b26f4cb5a1cf1528b4940315cd9e2c1c191cd`

Before manuscript analysis, independently stream the ledgers and verify:

1. byte hashes exactly match the seals;
2. row counts are 280,000 / 140,000 / 51,200 / 25,600;
3. evaluation IDs and feature-sufficient IDs are unique;
4. every evaluation carries the certified expected-index hash;
5. `p=(exceed_count+1)/1000` exactly and `reject == (exceed_count <= 49)`;
6. ALT rows carry the H0 phase-seal hash as `source_null_phase_seal_hash`;
7. per-cell replicate counts match 2,500 (H0) or 1,600 (H1);
8. regenerate cell × feature × method summaries directly from the sealed rows.

The supplied `audit_formal_ledgers.py` performs these checks using only the Python standard library and produces a JSON result plus per-cell summaries.

## 6. Final decision

```text
H0_RUN_BYTES_AND_SEALS        = STRUCTURALLY_COHERENT
H1_RUN_BYTES_AND_SEALS        = STRUCTURALLY_COHERENT
A_SCIENTIFIC_EXECUTION        = NO_NEW_BLOCKER_FOUND
B_TRIAL_IDENTITY              = PASS_AT_PLAN_SEAL_LEVEL
C_INDEPENDENT_RECOMPUTATION   = INCOMPLETE_UNTIL_RAW_LEDGER_STREAM_AUDIT
RERUN_H0                      = NO
RERUN_H1                      = NO
MANUSCRIPT_MAIN_AGGREGATION   = REGENERATE_FROM_SEALED_LEDGER
```

If the streaming raw-ledger audit passes, accept the current H0/H1 runs and move directly to the frozen analysis pipeline. Do not reopen crash-recovery, lock, mutation-battery or other engineering issues unless a concrete A/B/C failure is demonstrated.
