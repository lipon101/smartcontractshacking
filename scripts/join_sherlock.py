#!/usr/bin/env python3
"""Sherlock repo join — attach real audited contract code to Sherlock findings.

Finds the sherlock-audit GitHub repos for each corpus protocol, downloads the
contest tarballs, extracts the audited .sol files (tests/mocks/scripts/libs and
judging repos excluded), and writes splits/sherlock_joined.jsonl — one line per
protocol:

  {"protocol": "...", "repos": ["sherlock-audit/2023-03-teller", ...],
   "chars": N, "source": "// ===== <repo>/<path> ===== ..."}

build_splits.py consumes this file to fill the empty `source` field of every
Sherlock finding of that protocol (capped at MAX_FINDING_CHARS).

Repo matching: GitHub org repo list (API) -> strip the leading date token from
each repo name -> normalize (lowercase alnum) -> exact or containment match
against the normalized protocol name (min core length 4; exact for shorter).
Repos named *-judging are leaderboard archives, never contest code — excluded.

Usage:
  python3 scripts/join_sherlock.py            # writes splits/sherlock_joined.jsonl
  GITHUB_TOKEN=ghp_... python3 scripts/join_sherlock.py   # higher API rate limit

Requires network. Unauthenticated: org-repo list (60 req/hr) is enough.
"""
import glob
import io
import json
import os
import re
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

OWNER = "sherlock-audit"
MAX_FINDING_CHARS = 120_000          # per-finding source cap (prompt truncates at 6k anyway)
EXCLUDE_DIRS = {"test", "tests", "mock", "mocks", "script", "scripts",
                "node_modules", "lib", "forge-std", "ds-test"}
EXCLUDE_SUFFIXES = (".t.sol", ".s.sol", ".m.sol")   # foundry test/script modules

ROOT = os.getcwd() if os.path.isdir("splits") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLITS = os.path.join(ROOT, "splits")


def cat_jsonl(pattern):
    files = sorted(glob.glob(pattern))
    assert files, f"no files match {pattern}"
    rows, buf = [], b""
    for f in files:
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    rows.append(json.loads(line))
    return rows


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def repo_core(name):
    """Strip the leading contest-date token: '2023-03-teller' -> 'teller'."""
    return norm(re.sub(r"^\d{4}-\d{2}(-\d{2})?[-_]", "", name))


def is_sherlock(r):
    blob = ((r.get("slug") or "") + " " + (r.get("source_link") or "") + " " + (r.get("firm") or "")).lower()
    return "sherlock" in blob


def matches(protocol, repo_name):
    pn, rn = norm(protocol), repo_core(repo_name)
    if not pn or not rn:
        return False
    if pn == rn:
        return True
    if len(pn) >= 4 and (pn in rn or rn in pn):
        return True
    if len(pn) < 4 and pn in rn:
        return True
    return False


def fetch_repo_list(token):
    repos, page = [], 1
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    while True:
        r = requests.get(f"https://api.github.com/orgs/{OWNER}/repos",
                         params={"per_page": 100, "page": page}, headers=headers, timeout=60)
        if r.status_code == 401:
            print("token invalid — retrying unauthenticated")
            return fetch_repo_list(None)
        if r.status_code == 403:
            raise RuntimeError(f"github API rate limit: {r.text[:200]}")
        r.raise_for_status()
        batch = r.json()
        repos.extend({"name": b["name"], "branch": b.get("default_branch") or "main"} for b in batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def download_sol(repo, branch):
    """Return (source_text, n_files) of the repo's audited .sol files, or None on failure."""
    for try_branch in {branch, "main", "master"}:
        url = f"https://codeload.github.com/{OWNER}/{repo}/tar.gz/{try_branch}"
        try:
            r = requests.get(url, timeout=120)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        try:
            tf = tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz")
        except Exception:
            continue
        files = []
        for m in tf.getmembers():
            if not m.isfile():
                continue
            p = m.name.split("/", 1)[-1]                       # strip top-level dir
            parts = p.split("/")
            if not p.lower().endswith(".sol") or p.lower().endswith(EXCLUDE_SUFFIXES):
                continue
            if any(seg in EXCLUDE_DIRS for seg in parts[:-1]):
                continue
            try:
                files.append((p, tf.extractfile(m).read().decode("utf-8", errors="replace")))
            except Exception:
                continue
        files.sort()
        if files:
            src = "".join(f"// ===== {repo}/{p} =====\n{txt}\n" for p, txt in files)
            return src, len(files)
    return None, "download failed / no .sol files"


def main():
    token = os.environ.get("GITHUB_TOKEN", "").strip() or None

    # 1) sherlock rows without source, grouped by protocol
    rows = cat_jsonl(os.path.join(SPLITS, "train_source.jsonl.part*")) + cat_jsonl(os.path.join(SPLITS, "eval_source.jsonl"))
    by_prot = {}
    for r in rows:
        if r.get("source") or not is_sherlock(r):
            continue
        by_prot.setdefault(r["protocol"], []).append(r["id"])
    print(f"sherlock rows without source: {sum(len(v) for v in by_prot.values())} "
          f"across {len(by_prot)} protocols")

    # 2) org repo list + matching (judging repos are leaderboard archives — excluded)
    repos = [r for r in fetch_repo_list(token) if "judging" not in r["name"]]
    print(f"fetched {len(repos)} {OWNER} repos (judging repos excluded)")
    branch_of = {r["name"]: r["branch"] for r in repos}
    raw_matched = {p: [r["name"] for r in repos if matches(p, r["name"])] for p in by_prot}
    # one repo -> best-matching protocol (exact name wins, then longest core), so no
    # two protocols ever share identical source (cross-split code leakage risk)
    def _score(pp, repo):
        return (norm(pp) == repo_core(repo), len(norm(pp)))
    repo_owner = {}
    for pp, rl in raw_matched.items():
        for repo in rl:
            if repo not in repo_owner or _score(pp, repo) > _score(repo_owner[repo], repo):
                repo_owner[repo] = pp
    matched = {pp: [repo for repo in rl if repo_owner.get(repo) == pp]
               for pp, rl in raw_matched.items()}
    to_fetch = sorted({repo for rl in matched.values() for repo in rl})
    print(f"protocols with >=1 repo match: {sum(1 for v in matched.values() if v)} / {len(by_prot)} "
          f"| unique repos to fetch: {len(to_fetch)}")

    # 3) download tarballs in parallel
    sources, failures = {}, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(download_sol, repo, branch_of[repo]): repo for repo in to_fetch}
        for i, f in enumerate(as_completed(futs), 1):
            repo = futs[f]
            try:
                src, n = f.result()
            except Exception as e:
                src, n = None, str(e)[:200]
            if src:
                sources[repo] = src
                print(f"[{i}/{len(to_fetch)}] {repo}: {n} files, {len(src)//1000} KB")
            else:
                failures.append((repo, str(n)[:120]))
                print(f"[{i}/{len(to_fetch)}] {repo}: FAILED {str(n)[:120]}")

    # 4) build per-protocol source (only successfully downloaded repos, capped)
    out_rows, covered, skipped = [], 0, []
    for p, ids in by_prot.items():
        rl = [repo for repo in matched[p] if repo in sources]
        if not rl:
            skipped.append(p)
            continue
        src = "".join(sources[repo] for repo in rl)[:MAX_FINDING_CHARS]
        out_rows.append({"protocol": p, "repos": rl, "chars": len(src), "source": src})
        covered += len(ids)
    print(f"covered findings: {covered} | protocols written: {len(out_rows)} | unmatched: {len(skipped)}")

    out = os.path.join(SPLITS, "sherlock_joined.jsonl")
    with open(out, "w", encoding="utf-8") as fh:
        for row in out_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")

    report = {
        "sherlock_findings_without_source": sum(len(v) for v in by_prot.values()),
        "protocols": len(by_prot),
        "protocols_matched": len(out_rows),
        "protocols_unmatched": skipped,
        "repos_matched": len(to_fetch),
        "repos_downloaded": len(sources),
        "download_failures": failures,
        "findings_covered": covered,
    }
    rp = os.path.join(SPLITS, "sherlock_join_report.json")
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("unmatched protocols:", skipped)


if __name__ == "__main__":
    main()
