#!/usr/bin/env python3
"""Build Kaggle-ready train/eval splits + Code4rena source join (reproducible).

Pipeline (reproduces the shipped splits byte-for-byte in canonical mode):
  1. Load corpus/train_starter.jsonl.part*  -> 52,697 parsed findings (training schema)
  2. Dedupe by audit_text (keep first)      -> 51,823 records [matches split_report.json]
  3. Split (protocol-exclusive):
       default       : VERIFY the shipped canonical partition (splits/train.jsonl.part*
                       + splits/eval.jsonl) against the deduped corpus — id-set equality,
                       protocol exclusivity, contract-level leakage — then reuse it, so
                       the emitted files are byte-identical to the shipped ones.
       --rebuild-split: build a fresh deterministic split (seeded, protocol-level).
  4. Code4rena source join: fill `source` + `c4_repo` from splits/c4_joined.jsonl.part*
     by `id` (8,003 rows carry real audited contract code; nothing else is overwritten).
  5. Write splits/train_source.jsonl.partNN (byte-split, GitHub-friendly), splits/eval_source.jsonl,
     splits/split_report.json (stats + leakage proof + sha256 of every output).

Leakage guarantees (asserted AND reported): id overlap = 0, protocol overlap = 0,
(contract_name, protocol) overlap = 0, source-content (sha256) overlap = 0.

Usage:
  python3 scripts/build_splits.py                  # verify canonical + rebuild Kaggle-ready files
  python3 scripts/build_splits.py --rebuild-split  # fresh deterministic split instead
  python3 scripts/build_splits.py --out /tmp/rebuild   # write outputs elsewhere (dry-run)
  python3 scripts/build_splits.py --sort-keys yes|no   # json.dumps sort_keys (auto-detected)
"""
import argparse
import glob
import hashlib
import json
import os
import random
from collections import Counter, defaultdict

if "__file__" in globals() and os.path.isfile(__file__):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
else:
    ROOT = os.getcwd()   # exec()-probe mode: run from the repo root
PART_BYTES = 99_614_720  # 95 MiB chunks, matches the shipped byte-split layout


def cat_jsonl(pattern):
    """Parse a jsonl corpus, transparently reassembling byte-split .partNN files."""
    files = sorted(glob.glob(pattern))
    assert files, f"no files match {pattern}"
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
    if buf:
        line = buf.decode("utf-8").strip()
        if line:
            rows.append(json.loads(line))
    return rows


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def dump_row(row, sort_keys):
    return json.dumps(row, ensure_ascii=False, sort_keys=sort_keys)


def write_jsonl_parts(rows, path, sort_keys, part_bytes=PART_BYTES):
    """Write rows as one logical .jsonl, byte-split into .partNN files (cat part* restores it)."""
    payload = "".join(dump_row(r, sort_keys) + "\n" for r in rows).encode("utf-8")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    n_parts = (len(payload) + part_bytes - 1) // part_bytes
    for i in range(n_parts):
        chunk = payload[i * part_bytes:(i + 1) * part_bytes]
        with open(f"{path}.part{i:02d}", "wb") as fh:
            fh.write(chunk)
    return payload, n_parts


def write_jsonl(rows, path, sort_keys):
    payload = "".join(dump_row(r, sort_keys) + "\n" for r in rows).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(payload)
    return payload


def severity_counter(rows):
    return dict(Counter(r.get("severity") for r in rows))


def leakage_report(train, eval_):
    """id/protocol/contract-level/source-content leakage between two row sets."""
    tid = {r["id"] for r in train}
    eid = {r["id"] for r in eval_}
    tprot = {r["protocol"] for r in train}
    eprot = {r["protocol"] for r in eval_}
    tcp = {(r.get("contract_name"), r.get("protocol")) for r in train if r.get("contract_name")}
    ecp = {(r.get("contract_name"), r.get("protocol")) for r in eval_ if r.get("contract_name")}
    thash = {sha256_bytes((r.get("source") or "").encode()) for r in train if r.get("source")}
    ehash = {sha256_bytes((r.get("source") or "").encode()) for r in eval_ if r.get("source")}
    rep = {
        "id_overlap": len(tid & eid),
        "protocol_overlap": len(tprot & eprot),
        "contract_protocol_overlap": len(tcp & ecp),
        "source_hash_overlap": len(thash & ehash),
    }
    assert rep["id_overlap"] == 0, "id leakage!"
    assert rep["protocol_overlap"] == 0, "protocol leakage!"
    assert rep["contract_protocol_overlap"] == 0, "contract-level leakage!"
    assert rep["source_hash_overlap"] == 0, "source-content leakage!"
    return rep


def join_c4(rows, c4_by_id):
    """Fill source + c4_repo from c4_joined by id (only where real source exists)."""
    n = 0
    for r in rows:
        c = c4_by_id.get(r["id"])
        if c and c.get("source"):
            r["source"] = c["source"]
            r["c4_repo"] = c.get("c4_repo", "")
            n += 1
    return rows, n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "splits"), help="output dir (default: repo splits/)")
    ap.add_argument("--rebuild-split", action="store_true", help="build a fresh deterministic split instead of verifying the canonical one")
    ap.add_argument("--sort-keys", choices=("auto", "yes", "no"), default="auto", help="json.dumps sort_keys (auto: detected from shipped file)")
    ap.add_argument("--limit", type=int, default=None, help="cap rows (testing only)")
    args = ap.parse_args()

    # 1) corpus + dedup -----------------------------------------------------
    starter = cat_jsonl(os.path.join(ROOT, "corpus", "train_starter.jsonl.part*"))
    if args.limit:
        starter = starter[:args.limit]
    seen, dedup = set(), []
    for r in starter:
        k = r.get("audit_text")
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    print(f"[1] corpus = {len(starter)} -> dedup by audit_text = {len(dedup)} (removed {len(starter) - len(dedup)})")
    assert len(dedup) == 51823 or args.limit, "dedup count != published 51,823"

    # 2) split --------------------------------------------------------------
    if args.rebuild_split:
        # deterministic: protocols shuffled by a fixed seed, taken until ~10% of rows
        by_prot = defaultdict(list)
        for r in dedup:
            by_prot[r["protocol"]].append(r)
        order = sorted(by_prot.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        random.Random(42).shuffle(order)
        eval_rows, n = [], 0
        for p, rows in order:
            eval_rows.extend(rows)
            n += len(rows)
            if n >= 5190:
                break
        eval_ids = {r["id"] for r in eval_rows}
        train = [r for r in dedup if r["id"] not in eval_ids]
        eval_ = eval_rows
        print(f"[2] rebuild-split: train={len(train)} eval={len(eval_)} "
              f"(protocols {len({r['protocol'] for r in train})}/{len({r['protocol'] for r in eval_})})")
    else:
        train = cat_jsonl(os.path.join(ROOT, "splits", "train.jsonl.part*"))
        eval_ = cat_jsonl(os.path.join(ROOT, "splits", "eval.jsonl"))
        if args.limit:
            train, eval_ = train[:args.limit], eval_[:args.limit]
        canon_ids = {r["id"] for r in train} | {r["id"] for r in eval_}
        dedup_ids = {r["id"] for r in dedup}
        assert canon_ids == dedup_ids, "canonical split does not partition the deduped corpus!"
        print(f"[2] canonical split verified: train={len(train)} eval={len(eval_)} "
              f"| id set == deduped corpus ({len(canon_ids)})")

    # 3) Code4rena source join ----------------------------------------------
    c4 = cat_jsonl(os.path.join(ROOT, "splits", "c4_joined.jsonl.part*"))
    c4_by_id = {r["id"]: r for r in c4}
    train, n_tr = join_c4(train, c4_by_id)
    eval_, n_ev = join_c4(eval_, c4_by_id)
    print(f"[3] c4 source join: train {n_tr} rows, eval {n_ev} rows filled")

    # 4) leakage proof ------------------------------------------------------
    leak = leakage_report(train, eval_)
    print(f"[4] leakage: {leak}")

    # 5) write outputs ------------------------------------------------------
    sort_keys = {"yes": True, "no": False}.get(args.sort_keys)
    if sort_keys is None:
        # auto-detect from the shipped eval_source.jsonl (single file, no parts)
        shipped = open(os.path.join(ROOT, "splits", "eval_source.jsonl"), "rb").read()
        probe = eval_[0] if eval_ else {}
        sort_keys = dump_row(probe, True).encode() in shipped or not dump_row(probe, False).encode() in shipped
        print(f"[5] json.dumps sort_keys auto-detected = {sort_keys}")

    os.makedirs(args.out, exist_ok=True)
    tr_payload, tr_parts = write_jsonl_parts(train, os.path.join(args.out, "train_source.jsonl"), sort_keys)
    ev_payload = write_jsonl(eval_, os.path.join(args.out, "eval_source.jsonl"), sort_keys)
    print(f"[5] wrote {args.out}/train_source.jsonl.part00..{tr_parts - 1:02d} "
          f"({len(tr_payload) / 1e6:.1f} MB) + eval_source.jsonl ({len(ev_payload) / 1e6:.1f} MB)")

    # 6) report -------------------------------------------------------------
    eval_prot_sample = sorted({r["protocol"] for r in eval_})[:15]
    report = {
        "corpus_total": len(starter),
        "after_dedup": len(dedup),
        "dedup_removed": len(starter) - len(dedup),
        "dedup_key": "audit_text (keep first)",
        "split_mode": "canonical-verified" if not args.rebuild_split else "rebuild-seeded",
        "train_count": len(train),
        "eval_count": len(eval_),
        "eval_ratio": round(len(eval_) / len(dedup), 4),
        "train_protocols": len({r["protocol"] for r in train}),
        "eval_protocols": len({r["protocol"] for r in eval_}),
        "corpus_severity": severity_counter(dedup),
        "train_severity": severity_counter(train),
        "eval_severity": severity_counter(eval_),
        "c4_source_joined": {"train": n_tr, "eval": n_ev},
        "leakage": leak,
        "eval_protocols_sample": eval_prot_sample,
        "sha256": {
            "train_source.jsonl": sha256_bytes(tr_payload),
            "eval_source.jsonl": sha256_bytes(ev_payload),
        },
        "json_sort_keys": sort_keys,
    }
    with open(os.path.join(args.out, "split_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"[6] wrote {args.out}/split_report.json")
    print("train_source sha256:", report["sha256"]["train_source.jsonl"])
    print("eval_source  sha256:", report["sha256"]["eval_source.jsonl"])


if __name__ == "__main__":
    main()
