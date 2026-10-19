"""Live self-repair demo.

Copies the game to a temporary folder, deliberately breaks the copy, then lets the REAL AI
(your OpenAI key in ai-maintenance/.env) find and fix it through the normal weekly flow.
Your real repository is never touched.

    python ai-maintenance\\tests\\live_heal_demo.py
"""
import os, sys, json, shutil, subprocess, tempfile

FW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # .../ai-maintenance
PKG = os.path.dirname(FW)

def sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")

def main():
    d = tempfile.mkdtemp(prefix="beergame-heal-demo-"); aux = tempfile.mkdtemp(prefix="beergame-heal-aux-")
    try:
        shutil.copytree(PKG, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
            ".git", "twin", "state", "reports", "__pycache__", "node_modules", ".env", "package-lock.json"))
        # 1. break the copy: one syntax error inside engine.js
        eng = os.path.join(d, "source", "engine.js")
        src = open(eng, encoding="utf-8", newline="").read().replace("\r\n", "\n")
        lines = src.split("\n")
        i = next(n for n, l in enumerate(lines) if l.startswith("function ") and l.rstrip().endswith("{"))
        lines.insert(i + 1, "  const brokenOnPurpose = ;")
        open(eng, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        print("Broke a copy of the game: source/engine.js line %d now has a syntax error." % (i + 2))
        # 2. make it a git repo with the dev/test/main branches
        sh("git init -q -b main && git config core.autocrlf false && git config user.email demo@example.com && git config user.name demo"
           " && git add -A && git commit -qm broken && git branch dev && git branch test", d)
        # 3. run the real weekly flow on the copy (no pushing, no live release)
        c = json.load(open(os.path.join(FW, "config", "config.json"), encoding="utf-8")); c["git"]["push"] = False; c["proactive"]["enabled"] = False   # this demo is only about repair
        cfg = os.path.join(aux, "cfg.json"); open(cfg, "w", encoding="utf-8").write(json.dumps(c))
        env = dict(os.environ, PORTAL_REPO=d, AGENT_CONFIG=cfg, AGENT_STATE_DIR=os.path.join(aux, "s"), AGENT_REPORTS_DIR=os.path.join(aux, "r"))
        print("Asking the AI to repair it (this uses your OpenAI key and takes a minute)...\n")
        r = subprocess.run([sys.executable, os.path.join(FW, "agent", "maintain.py"), "weekly"], cwd=d, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(r.stdout + r.stderr)
        # 4. verdict
        fixed = "const brokenOnPurpose = ;" not in sh("git show test:source/engine.js", d).stdout   # the broken line is gone from the test environment
        print("-" * 60)
        if fixed:
            print("RESULT: PASS - the AI fixed the broken code and it reached the test environment.")
            print(sh("git diff main test -- source", d).stdout)
        else:
            print("RESULT: NOT FIXED - see the output above for why (key, credit, or the AI's answer).")
        return 0 if fixed else 1
    finally:
        shutil.rmtree(d, ignore_errors=True); shutil.rmtree(aux, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
