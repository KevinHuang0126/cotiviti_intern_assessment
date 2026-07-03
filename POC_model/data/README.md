# NCD 210.14 Data Artifacts

**Policy:** Lung Cancer Screening with Low Dose Computed Tomography (LDCT)  
**NCD ID:** 364  
**Source:** [Medicare Coverage Database](https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?NCDId=364)

## Versions

| Version | CAG | Effective |
|---------|-----|-----------|
| v1 | CAG-00439N | 2015-02-05 – 2022-02-10 |
| v2 | CAG-00439R | 2022-02-10 – present |

## Files

- `coverage_section_v1.md` — Hand-trimmed coverage criteria (2015), consumed by Compiler
- `coverage_section_v2.md` — Hand-trimmed coverage criteria (2022), consumed by Compiler

Full PDFs can be downloaded from the MCD Version History tab. Text extraction uses `src/pdf_extract.py`.

## Verified threshold wording (2026-06-30)

| Criterion | v1 verbatim | v2 verbatim |
|-----------|-------------|-------------|
| Age | "55 – 77 years" | "Age 50 - 77 years" |
| Pack-years | "at least 30 pack-years" | "at least 20 pack-years" |
| LDCT code | HCPCS G0297 | CPT 71271 |
| SDM visit | HCPCS G0296 | HCPCS G0296 (stable) |
