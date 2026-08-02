SOLODIT FULL CORPUS — 52,697 findings (verified 2026-08-02)
Source: https://solodit.cyfrin.io  (official Findings API, POST /api/v1/solodit/findings)
Filters: impact HIGH/MEDIUM/LOW/GAS · sort: Recency desc · 527 pages × up to 100

CONTENTS
  findings.jsonl .............. 52,697 findings, one full API record per line (byte-exact, no cutoffs)
  train_starter.jsonl ......... 52,697 training rows (id/slug/source_link provenance + full audit_text)
  solodit_full_corpus.zip ..... nested archive: raw/ + findings.jsonl + state.json
  raw/ ........................ 527 raw API pages (page_00001..page_00527)
  state.json .................. resume state (all 527 pages fetched)
  sample_review.md ............ the manual-review sample (Shieldify [L-03], matches source exactly)

INTEGRITY (verified programmatically)
  records = 52,697 · unique ids = 52,697 · API total = 52,697
  63 records have empty content — verified EMPTY IN THE API ITSELF (byte-identical re-fetch), not truncation
  saved pages byte-identical to live API responses

SHA256
  findings.jsonl      3470ffbebe03671f0926865a6b8608ece910be24d2efcbc8869436a19472b3b5
  train_starter.jsonl 15374b70fe309e445ab1c7f84b3a7dab5752b6b1fcdf96e7e9d8647e7f289ed9
