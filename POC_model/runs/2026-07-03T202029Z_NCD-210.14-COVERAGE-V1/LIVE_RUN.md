# Live run — provenance

**This run was produced against the real Anthropic API** (`make demo-live`, `--demo-mode live`), not fixtures/replay.

- **Date:** 2026-07-03 (UTC 20:20:29, dir timestamp)
- **Policy:** NCD-210.14 CAG-00439N (V1)
- **Models:** Compiler/Fixer = claude-sonnet-5, Adversary = claude-haiku-4-5
- **Outcome:** converged in 2 rounds; final rule hash `555475b101f9feb0`

## Round-by-round
- Round 1: failures=2, rule_hash=`2623fb89434dfb8c`
    - fix: {"change": "Corrected age leaf minimum from 50 to 55 to match cited policy text.", "cite": "The beneficiary must be age 55 \u2013 77 years.", "reason": "Source text explicitly states minimum age of 55; prior rule had a transcription error (50) that caused ADV-001-age-54 to incorrectly approve a 54-year-old."}
    - fix: {"change": "Removed G0296 from the procedure_covered code_set leaf so that the code_set condition requires G0297 (LDCT screening) specifically as the billable screening procedure, while G0296 remains referenced via the sdm-visit-order documentation requirement.", "cite": "Covered procedure codes include HCPCS G0296 (counseling/SDM visit) and HCPCS G0297 (LDCT lung cancer screening).", "reason": "ADV-014 shows a claim with only G0296 (no G0297) was incorrectly approved. The screening procedure code G0297 must be present for the LDCT screening to be covered; requiring it in the code_set leaf enforces this while G0296 is still tracked through the SDM visit documentation requirement."}
- Round 2: failures=0, rule_hash=`555475b101f9feb0`

## Note
This is a **non-deterministic live verification**, kept as evidence the pipeline runs end-to-end against the live API. It is intentionally NOT the canonical demo: the reproducible demo is the fixture/replay run backing the report. Live runs converge to valid-but-different rules, which is why the coverage decision is made by the deterministic engine over a citation-checked rule.
