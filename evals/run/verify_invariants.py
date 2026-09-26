"""
verify_invariants.py — automated invariant checks for the agent harness.

Run AFTER an agent finishes a task to verify process compliance:
  1. pytest suite is green
  2. if decision-path files changed vs a base ref, docs/BACKTEST_LOG.md
     must contain a dated entry newer than that ref (or be untouched because
     the change was reverted — reported, not enforced)
  3. no secrets patterns in the working diff
  4. no temp/scratch files left behind
  5. resources/technical_config.json still parses

Usage:
  python evals/run/verify_invariants.py [--base-ref HEAD~1] [--skip-tests]

Exit code 0 = all checks pass; 1 = at least one failure.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DECISION_PATH_FILES = [
    "tools/technical_engine.py",
    "tools/custom_financial_calc.py",
    "tools/risk_management.py",
    "tools/news_sentiment.py",
    "tools/google_handler.py",
    "main.py",
    "resources/technical_config.json",
]

SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}",
    r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
    r'"private_key"\s*:',
]

TEMP_FILE_PATTERNS = [r"^_.*\.py$", r".*\.env$"]


def sh(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, shell=isinstance(cmd, str))


def check_tests(skip):
    if skip:
        return True, "skipped (--skip-tests)"
    r = sh(["python", "-m", "pytest", "test/", "-q"])
    ok = r.returncode == 0
    tail = (r.stdout + r.stderr).strip().splitlines()
    return ok, tail[-1] if tail else "no output"


def check_engine_change_log(base_ref):
    r = sh(["git", "diff", "--name-only", base_ref, "--"] + DECISION_PATH_FILES)
    changed = [f for f in r.stdout.splitlines() if f.strip()]
    if not changed:
        return True, f"no decision-path files changed vs {base_ref}"
    r2 = sh(["git", "diff", "--name-only", base_ref, "--", "docs/BACKTEST_LOG.md"])
    logged = bool(r2.stdout.strip())
    if logged:
        return True, f"engine files changed ({', '.join(changed)}) and BACKTEST_LOG.md updated"
    return False, (
        f"engine files changed ({', '.join(changed)}) but docs/BACKTEST_LOG.md "
        "was NOT updated — policy violation unless the change was reverted"
    )


def check_secrets(base_ref):
    r = sh(["git", "diff", base_ref, "--"])
    diff = r.stdout
    added = "\n".join(l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    hits = [p for p in SECRET_PATTERNS if re.search(p, added)]
    if hits:
        return False, f"possible secret material in added lines (patterns: {hits})"
    return True, "no secret patterns in diff"


def check_temp_files():
    r = sh(["git", "status", "--porcelain"])
    bad = []
    for line in r.stdout.splitlines():
        path = line[3:].strip().strip('"')
        base = os.path.basename(path)
        if any(re.match(p, base) for p in TEMP_FILE_PATTERNS):
            bad.append(path)
    if bad:
        return False, f"temp/scratch files present: {bad}"
    return True, "no temp files"


def check_config():
    path = os.path.join(ROOT, "resources", "technical_config.json")
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
        return True, "technical_config.json parses"
    except Exception as e:
        return False, f"technical_config.json invalid: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-ref", default="HEAD")
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()

    checks = [
        ("pytest suite", check_tests(args.skip_tests)),
        ("engine change vs BACKTEST_LOG", check_engine_change_log(args.base_ref)),
        ("no secrets in diff", check_secrets(args.base_ref)),
        ("no temp files", check_temp_files()),
        ("config parses", check_config()),
    ]

    width = max(len(n) for n, _ in checks)
    failures = 0
    for name, (ok, detail) in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"[{status}] {name:<{width}} — {detail}")

    print()
    print("RESULT:", "ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
