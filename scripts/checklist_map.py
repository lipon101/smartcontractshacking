#!/usr/bin/env python3
"""Map the Findings Checklist categories onto the corpus (vuln_type / audit_text).

Single source of truth for the category -> regex-pattern mapping used by:
  - docs/checklist_vuln_type_map.json   (coverage stats, --corpus mode)
  - kaggle_finetune.ipynb               (prompt-context injection; the notebook
                                         embeds copies of both pattern tiers at
                                         build time so it stays self-contained)

Two tiers (refined by two precision audits; audit_text-only matching was noisy,
e.g. "donat" / "signature" / "callback" / "predictable" substring hits, so the
audit tier now contains only strict phrases):

  CHECKLIST_PATTERNS       -> matched against vuln_type (broad, high signal)
  CHECKLIST_AUDIT_PATTERNS -> matched against audit_text (strict phrases only)

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
        r"donation attack", r"donat\w* (tokens?|funds?)", r"first depositor",
        r"balanceof", r"internal accounting",
    ],
    "Front-running Attack": [
        r"front[- ]?run", r"frontrun", r"mempool", r"commit[- ]?reveal",
        r"get[- ]?or[- ]?create", r"preempt", r"two[- ]transaction",
    ],
    "Griefing Attack": [
        r"grief", r"force (a )?(revert|failure)", r"prevent (the )?(withdrawal|repayment)",
        r"spam",
    ],
    "Miner Attack": [
        r"block\.timestamp", r"\btimestamp", r"block\.number", r"randomness",
        r"\bminer", r"transaction order", r"tx order", r"\bpredictable",
    ],
    "Price Manipulation Attack": [
        r"\bprice", r"\boracle", r"\btwap", r"flash[- ]?loan", r"spot price",
        r"liquidity pool", r"ratio of token balances", r"manipulat",
    ],
    "Reentrancy Attack": [
        r"reentran", r"read[- ]?only reentran", r"check[- ]?effects[- ]?interactions",
        r"state change after interaction",
    ],
    "Replay Attack": [
        r"replay", r"\bnonce", r"chainid", r"chain id", r"eip-712", r"signature replay",
    ],
    "Rug Pull": [
        r"rug", r"pull (all |the )?(assets|funds|tokens)", r"admin.*(pull|withdraw|steal)",
        r"owner.*(pull|withdraw|steal)", r"pull assets", r"no (way|functionality) to withdraw",
    ],
    "Sandwich Attack": [
        r"sandwich", r"slippage", r"min(imum)? (output|amount)", r"minout", r"min out",
    ],
    "Sybil Attack": [
        r"sybil", r"quorum", r"number of users", r"unique users",
    ],
}

CHECKLIST_AUDIT_PATTERNS = {
    "Denial-Of-Service (DoS) Attack": [
        r"denial of service", r"out of gas", r"unbounded loop",
        r"withdrawal pattern", r"pull[- ]?based", r"low decimal",
        r"blacklist", r"grief",
    ],
    "Donation Attack": [
        r"donation attack", r"internal accounting",
    ],
    "Front-running Attack": [
        r"front[- ]?run", r"frontrun", r"commit[- ]?reveal", r"mempool", r"preempt",
    ],
    "Griefing Attack": [
        r"grief",
    ],
    "Miner Attack": [
        r"block\.timestamp", r"block\.number", r"randomness",
    ],
    "Price Manipulation Attack": [
        r"price manipulation", r"oracle manipulation", r"oracle price",
        r"flash[- ]?loan", r"\btwap", r"spot price",
    ],
    "Reentrancy Attack": [
        r"reentran", r"read[- ]?only reentran", r"check[- ]?effects[- ]?interactions",
    ],
    "Replay Attack": [
        r"signature replay", r"replay attack", r"nonce reuse", r"chainid", r"eip-712",
    ],
    "Rug Pull": [
        r"rug pull", r"admin (can )?(pull|withdraw|steal)",
    ],
    "Sandwich Attack": [
        r"sandwich", r"slippage", r"min(imum)? (output|amount)",
    ],
    "Sybil Attack": [
        r"sybil", r"quorum",
    ],
}

_VT = {cat: [re.compile(p, re.IGNORECASE) for p in pats] for cat, pats in CHECKLIST_PATTERNS.items()}
_AT = {cat: [re.compile(p, re.IGNORECASE) for p in pats] for cat, pats in CHECKLIST_AUDIT_PATTERNS.items()}


def match_categories(vuln_type, audit_text=""):
    """Checklist categories whose vuln_type pattern or strict audit phrase hits."""
    hits = []
    for cat, res in _VT.items():
        for rx in res:
            if rx.search(vuln_type or ""):
                hits.append(cat)
                break
    if audit_text:
        at = audit_text[:2000]
        for cat, res in _AT.items():
            if cat in hits:
                continue
            for rx in res:
                if rx.search(at):
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
    vt_hits = Counter()          # matched on vuln_type alone
    at_only_hits = Counter()     # matched only via the strict audit tier
    examples = {c: [] for c in CHECKLIST_PATTERNS}
    matched_records = 0
    unmatched = []

    for r in rows:
        vt = r.get("vuln_type") or ""
        at = (r.get("audit_text") or "")[:2000]
        cats = match_categories(vt, at)
        if cats:
            matched_records += 1
            vt_cats = [c for c in cats if any(rx.search(vt) for rx in _VT[c])]
            for c in cats:
                per_cat[c] += 1
                if c in vt_cats:
                    vt_hits[c] += 1
                else:
                    at_only_hits[c] += 1
                if len(examples[c]) < 12 and vt.strip():
                    examples[c].append(vt.strip()[:160])
        elif len(unmatched) < 20:
            unmatched.append((vt.strip() or "(empty vuln_type)")[:160])

    report = {
        "corpus": args.corpus,
        "records": n,
        "matched_records": matched_records,
        "matched_pct": round(100.0 * matched_records / n, 2),
        "note": "Two-tier matching: CHECKLIST_PATTERNS on vuln_type + strict "
                "CHECKLIST_AUDIT_PATTERNS on audit_text (keyword-heuristic; weak supervision).",
        "categories": {
            c: {
                "patterns": CHECKLIST_PATTERNS[c],
                "audit_patterns": CHECKLIST_AUDIT_PATTERNS[c],
                "records": per_cat[c],
                "pct_of_corpus": round(100.0 * per_cat[c] / n, 2),
                "via_vuln_type": vt_hits[c],
                "via_audit_only": at_only_hits[c],
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
