#!/usr/bin/env python3
"""Map the Findings Checklist categories onto the corpus (vuln_type / audit_text).

Single source of truth for the category -> regex-pattern mapping used by:
  - docs/checklist_vuln_type_map.json   (coverage stats, --corpus mode)
  - kaggle_finetune.ipynb               (prompt-context injection; the notebook
                                         embeds a copy of CHECKLIST_PATTERNS at
                                         build time so it stays self-contained)

Usage:
  python3 scripts/checklist_map.py --corpus splits/train_source.jsonl --out docs/checklist_vuln_type_map.json

The loader transparently reassembles byte-split parts (train_source.jsonl.partNN,
true `cat part*` semantics — a record straddling a part boundary is reassembled
before line-splitting), matching the notebook's loader.
"""
import argparse
import glob
import json
import re
from collections import Counter

# Category names MUST match docs/findings_checklist.json "categories[].name".
CHECKLIST_PATTERNS = {
    "Denial-Of-Service (DoS) Attack": [
        r"\bdos\b", r"denial of service", r"denial-of-service",
        r"withdraw(al)? pattern", r"pull[- ]?based", r"\bdust", r"queue",
        r"low decimal", r"blacklist", r"grief", r"out of gas", r"block gas",
        r"unbounded loop", r"gas limit",
    ],
    "Donation Attack": [
        r"(?s)donat\\w*.{0,30}(attack|inflate|manipulat|tokens?|funds?|balance|pool|price|account)",
        r"balanceof", r"internal accounting",
    ],
    "Front-running Attack": [
        r"front[- ]?run", r"mempool", r"commit[- ]?reveal", r"get[- ]?or[- ]?create",
        r"preempt", r"two[- ]transaction",
    ],
    "Griefing Attack": [
        r"grief", r"gas limit", r"force (a )?(revert|failure)", r"prevent (the )?(withdrawal|repayment)",
    ],
    "Miner Attack": [
        r"block\.timestamp", r"\btimestamp", r"block\.number", r"randomness",
        r"\bminer", r"transaction order", r"tx order", r"predictable",
    ],
    "Price Manipulation Attack": [
        r"\bprice", r"\boracle", r"\btwap", r"flash[- ]?loan", r"spot price",
        r"liquidity pool", r"ratio of token balances", r"manipulat",
    ],
    "Reentrancy Attack": [
        r"reentran", r"callback", r"check[- ]?effects[- ]?interactions",
        r"state change after interaction", r"read[- ]?only reentran",
    ],
    "Replay Attack": [
        r"replay", r"\bnonce", r"chainid", r"chain id", r"eip-712", r"signature",
    ],
    "Rug Pull": [
        r"rug", r"pull (all |the )?(assets|funds|tokens)", r"admin.*(pull|withdraw|steal)",
        r"owner.*(pull|withdraw|steal)", r"pull assets",
    ],
    "Sandwich Attack": [
        r"sandwich", r"slippage", r"min(imum)? (output|amount)", r"minout", r"min out",
    ],
    "Sybil Attack": [
        r"sybil", r"quorum", r"number of users", r"unique users",
    ],
}

_COMPILED = {
    cat: [re.compile(p, re.IGNORECASE) for p in pats]
    for cat, pats in CHECKLIST_PATTERNS.items()
}


def match_categories(*texts):
    """Return checklist categories whose patterns hit any of the given texts."""
    hits = []
    for cat, res in _COMPILED.items():
        for rx in res:
            if any(rx.search(t) for t in texts if t):
                hits.append(cat)
                break
    return hits


def load_jsonl(path, limit=None):
    """Parse a jsonl corpus; transparently reassembles byte-split .partNN files
    (cat part* semantics, straddling records reassembled before line-splitting)."""
    files = sorted(glob.glob(path + "*"))
    assert files, f"no files match {path}*"
    rows = []
    buf = b""
    for f in files:
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.decode("utf-8").strip()
                    if line:
                        rows.append(json.loads(line))
                        if limit and len(rows) >= limit:
                            return rows
    if buf:
        line = buf.decode("utf-8").strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True, help="path to a corpus jsonl (splits/train_source.jsonl)")
    ap.add_argument("--out", help="write the coverage report JSON here")
    ap.add_argument("--limit", type=int, default=None, help="cap rows for quick runs")
    args = ap.parse_args()

    rows = load_jsonl(args.corpus, args.limit)
    n = len(rows)
    per_cat = Counter()
    examples = {c: [] for c in CHECKLIST_PATTERNS}
    matched_records = 0
    unmatched = []

    for r in rows:
        vt = r.get("vuln_type") or ""
        at = (r.get("audit_text") or "")[:2000]
        cats = match_categories(vt, at)
        if cats:
            matched_records += 1
            for c in cats:
                per_cat[c] += 1
                if len(examples[c]) < 12 and vt.strip():
                    examples[c].append(vt.strip()[:160])
        elif len(unmatched) < 20:
            unmatched.append((vt.strip() or "(empty vuln_type)")[:160])

    report = {
        "corpus": args.corpus,
        "records": n,
        "matched_records": matched_records,
        "matched_pct": round(100.0 * matched_records / n, 2),
        "categories": {
            c: {
                "patterns": CHECKLIST_PATTERNS[c],
                "records": per_cat[c],
                "pct_of_corpus": round(100.0 * per_cat[c] / n, 2),
                "example_vuln_types": examples[c],
            }
            for c in CHECKLIST_PATTERNS
        },
        "unmatched_examples": unmatched,
    }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("wrote", args.out)
    print(text)


if __name__ == "__main__":
    main()
