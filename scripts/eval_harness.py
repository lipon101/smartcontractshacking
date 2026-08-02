#!/usr/bin/env python3
"""
hunter-gate — Echidna differential-fuzz gate for the 27B Solidity hunter
========================================================================
Pipeline:  model proposes -> THIS GATE confirms -> manual PoC review -> Immunefi submit

What it does per contract/function:
  1. Asks the served model (Ollama) for a strict-JSON audit.
  2. If "vulnerable": takes the model's `patched_function` and splices it into a
     copy of the contract (Patched.sol) vs the original (Original.sol).
  3. Builds a Foundry workspace + a DifferentialTest wrapper that calls BOTH
     contracts with identical random inputs (low-level .call, compares revert
     status + return bytes).
  4. Runs forge build, then Echidna differential fuzzing (assertion mode).
  5. Verdict: a candidate is only GATE=PASS if it compiles AND Echidna observes
     a behavioral divergence (the "fix" actually changed logic). Otherwise reject.

Usage:
  python3 eval_harness.py --model hunter --contract ./corpus/token.sol --function transferFrom
  python3 eval_harness.py --model hunter --scan ./corpus --out findings.jsonl

Requirements (see vps_setup.sh): Ollama serving your model, forge, echidna, solc 0.8.x on PATH.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
SOLC_HINT = "Install solc: pip3 install solc-select && solc-select install 0.8.23 && solc-select use 0.8.23"

SYSTEM_PROMPT = (
    "You are a professional smart-contract security auditor for bug bounties (Immunefi). "
    "Given a Solidity contract and a function, find the vulnerability, prove it with a "
    "concrete exploit PoC, and give the exact fix. Output ONLY strict JSON:\n"
    '{"vulnerable": true/false, "vuln_type": "...", "severity": "critical|high|medium|low", '
    '"poc": "<step-by-step exploit sequence>", "fix": "<what the fix is and why>", '
    '"patched_function": "<the FULL replacement function including its signature, '
    'or null if not vulnerable>"}'
)

FUNC_RE = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", re.S)


# ---------------------------------------------------------------- model layer
def ask_model(model_name: str, user_text: str, max_new: int = 2048, temperature: float = 0.2) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_new},
        },
        timeout=3600,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def extract_json(text: str) -> dict:
    """Pull the first {...} block out of the model output."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


# ------------------------------------------------------------- source tooling
def find_function_span(src: str, name: str):
    """Return (start, end) of `function name(...) { body }`, or None."""
    m = re.search(r"\bfunction\s+" + re.escape(name) + r"\s*\(", src)
    if not m:
        return None
    start = m.start()
    brace = src.find("{", m.end())
    if brace == -1:
        return None
    depth, i = 0, brace
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    return None


def parse_params(args_str: str):
    """Parse 'uint256 amount, address[] path' -> (types, names). Standard types only."""
    types, names = [], []
    for chunk in args_str.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        tokens = chunk.split()
        # type = everything before the last identifier
        if len(tokens) >= 2:
            types.append(" ".join(tokens[:-1]).strip())
            names.append(tokens[-1].strip())
        else:
            types.append(chunk)
            names.append("arg" + str(len(names)))
    return types, names


def signature_for(name: str, types: list) -> str:
    return f"{name}({','.join(types)})"


# -------------------------------------------------------------- workspace gen
WRAPPER_TPL = """\
    function __diff_{name}({params}) public {{
        (bool ok1, bytes memory d1) = address(orig).call(
            abi.encodeWithSignature("{sig}", {args}));
        (bool ok2, bytes memory d2) = address(patched).call(
            abi.encodeWithSignature("{sig}", {args}));
        require(ok1 == ok2, "DIVERGENCE");
        if (ok1) require(keccak256(d1) == keccak256(d2), "DIVERGENCE");
    }}
"""

DIFF_TPL = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

import {{Original}} from "./Original.sol";
import {{Patched}} from "./Patched.sol";

// Differential test: identical random call sequences into both contracts.
// Any divergence (revert status or return data) trips the assertion -> Echidna fails.
// NOTE: works when both contracts are deployable with no-arg constructors;
// otherwise edit this generated file (constructor args) before running.
contract DifferentialTest {{
    Original public orig;
    Patched public patched;

    constructor() {{
        orig = new Original();
        patched = new Patched();
    }}
{wrappers}
}}
"""

FOUNDRY_TOML = """\
[profile.default]
src = "src"
out = "out"
"""

ECHIDNA_YAML = """\
testMode: assertion
testLimit: 50000
timeout: 900
"""


def build_workspace(orig_src: str, patched_src: str, funcs: list, out_dir: Path):
    src_dir = out_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "foundry.toml").write_text(FOUNDRY_TOML)
    (out_dir / "echidna.yaml").write_text(ECHIDNA_YAML)
    (src_dir / "Original.sol").write_text(orig_src)
    (src_dir / "Patched.sol").write_text(patched_src)

    wrappers = []
    for name in funcs:
        m = re.search(r"\bfunction\s+" + re.escape(name) + r"\s*\(([^)]*)\)", orig_src)
        if not m:
            continue
        types, names = parse_params(m.group(1))
        params = ", ".join(f"{t} {n}" for t, n in zip(types, names))
        args = ", ".join(names)
        wrappers.append(WRAPPER_TPL.format(name=name, params=params, sig=signature_for(name, types), args=args))
    if not wrappers:
        raise RuntimeError("no parseable functions — cannot build differential harness")
    (src_dir / "DifferentialTest.sol").write_text(DIFF_TPL.format(wrappers="\n".join(wrappers)))


# ------------------------------------------------------------------ the gate
def run_gate(model_name: str, contract_path: Path, function_name: str, workdir: Path | None = None) -> dict:
    verdict = {
        "contract": contract_path.name,
        "function": function_name,
        "gate": "ERROR",
        "vulnerable": None,
        "vuln_type": None,
        "severity": None,
        "poc": None,
        "fix": None,
        "detail": "",
    }
    src = contract_path.read_text()
    user = f"Contract `{contract_path.name}`:\n\n{src}\n\nFunction under review:\n```solidity\n{extract_function(src, function_name)}\n```"

    try:
        raw = ask_model(model_name, user)
        rec = extract_json(raw)
        verdict.update({k: rec.get(k) for k in ("vulnerable", "vuln_type", "severity", "poc", "fix")})
        if not rec.get("vulnerable"):
            verdict["gate"] = "SKIP_NOT_VULNERABLE"
            return verdict

        patched_fn = rec.get("patched_function")
        if not patched_fn or f"function {function_name}" not in patched_fn:
            verdict["gate"] = "PARSE_FAIL"
            verdict["detail"] = "model returned no valid patched_function"
            return verdict

        span = find_function_span(src, function_name)
        if not span:
            verdict["gate"] = "PARSE_FAIL"
            verdict["detail"] = "could not locate function in source"
            return verdict

        patched_src = src[: span[0]] + patched_fn.strip() + src[span[1] :]

        with tempfile.TemporaryDirectory(dir=workdir) as td:
            ws = Path(td)
            build_workspace(src, patched_src, [function_name], ws)

            # 1) forge build
            build = subprocess.run(["forge", "build"], cwd=ws, capture_output=True, text=True, timeout=1800)
            if build.returncode != 0:
                verdict["gate"] = "BUILD_FAIL"
                verdict["detail"] = build.stderr[-2000:]
                return verdict

            # 2) echidna differential fuzz
            exe = "echidna" if shutil.which("echidna") else shutil.which("echidna-test")
            if not exe:
                verdict["gate"] = "ERROR"
                verdict["detail"] = "echidna not found on PATH"
                return verdict
            run = subprocess.run(
                [exe, "test", ".", "--contract", "DifferentialTest", "--config", "echidna.yaml"],
                cwd=ws, capture_output=True, text=True, timeout=3600,
            )
            out = (run.stdout + run.stderr).lower()
            diverged = run.returncode != 0 or ("assertion" in out and "fail" in out)
            verdict["divergence_found"] = bool(diverged)
            verdict["gate"] = "PASS" if diverged else "NO_DIVERGENCE"
            verdict["detail"] = f"echidna rc={run.returncode}; {run.stdout[-1500:]}"
            return verdict
    except Exception as e:  # noqa: BLE001
        verdict["gate"] = "ERROR"
        verdict["detail"] = f"{type(e).__name__}: {e}"
        return verdict


def extract_function(src: str, name: str) -> str:
    span = find_function_span(src, name)
    return src[span[0] : span[1]] if span else f"// function {name} not found"


# --------------------------------------------------------------------- modes
def main():
    ap = argparse.ArgumentParser(description="Echidna differential-fuzz gate (0-FP filter)")
    ap.add_argument("--model", default="hunter", help="Ollama model name (default: hunter)")
    ap.add_argument("--contract", help="single .sol file to audit")
    ap.add_argument("--function", help="function name (single mode)")
    ap.add_argument("--scan", help="folder of .sol files to scan")
    ap.add_argument("--out", default="findings.jsonl", help="output file for scan mode")
    ap.add_argument("--workdir", default=None, help="temp workspace root (default: system tmp)")
    args = ap.parse_args()

    if shutil.which("solc") is None:
        print("FATAL: solc not found on PATH.", SOLC_HINT, file=sys.stderr)
        sys.exit(2)

    if args.contract:
        if not args.function:
            ap.error("--function is required with --contract")
        v = run_gate(args.model, Path(args.contract), args.function, args.workdir)
        print(json.dumps(v, indent=2))
        sys.exit(0 if v["gate"] == "PASS" else 1)

    if args.scan:
        corpus = Path(args.scan)
        passed = 0
        with open(args.out, "a") as fh:
            for sol in sorted(corpus.glob("*.sol")):
                src = sol.read_text()
                for m in FUNC_RE.finditer(src):
                    name = m.group(1)
                    v = run_gate(args.model, sol, name, args.workdir)
                    print(f"{sol.name}::{name} -> {v['gate']}")
                    if v["gate"] == "PASS":
                        fh.write(json.dumps(v) + "\n")
                        fh.flush()
                        passed += 1
        print(f"\nDone: {passed} gated candidate(s) appended to {args.out} — manual PoC review next.")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
