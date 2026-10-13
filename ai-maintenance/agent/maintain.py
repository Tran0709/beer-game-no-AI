"""The AI maintenance agent.
  python agent/maintain.py weekly                   scheduled upkeep
  python agent/maintain.py feedback --text "..."    fix something a human reported
Flow: branch off dev -> run upkeep tasks -> run tests -> if red, ask the AI for a patch (guardrailed)
      -> commit -> promote dev -> test(twin) -> live gate -> report to Telegram."""
import sys, os, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *
import pipeline, review

SYSTEM = ("You are a careful maintenance engineer for The Beer Game, a single-file browser simulation (sources in source/*.js and base-style.css; index.html is generated, never edit it). "
          "Make the smallest change that fixes the problem, using ONLY text you can see in the excerpts provided. " + EDIT_FORMAT_HELP + " "
          "Never touch secrets, .env, CI files, tests or ai-maintenance/. If you cannot fix it safely, reply with exactly: NO_SAFE_FIX")

def dirty():
    """Uncommitted changes, ignoring the agent's own folder (reports, state)."""
    return git("status", "--porcelain", "--", ".", ":!ai-maintenance")

def toast_for(applied, suggestions, ok, lines, fixed):
    """A short, useful desktop notification: lead with what happened, not the routine task lines."""
    if not ok: return "A change FAILED its checks and was rolled back. Details: ai-maintenance/reports."
    parts = []
    n = len(applied) + (1 if fixed else 0)
    if any("waiting for your approval" in l for l in lines): parts.append("%d change(s) ready, waiting for your approval (/approve)" % max(n, 1))
    elif any(l.startswith("LIVE:") and "tests: PASS" in l for l in lines): parts.append("Changes are live")
    if fixed: parts.append("Fixed a failing check")
    if applied: parts.append("Applied: " + "; ".join(x.split(":")[0] for x in applied))
    if not parts: parts.append("No changes made")
    if suggestions: parts.append("%d suggestion(s) for you: %s" % (len(suggestions), "; ".join(x.split(":")[0] for x in suggestions)))
    return " | ".join(parts)

def try_patch(problem, out, g, report):
    ask = lambda q: ask_llm(q, "Answer exactly as instructed.")
    for attempt in range(1, g["max_fix_attempts"] + 1):
        try:
            ctx = file_context(problem + "\n" + out[-3000:], ask)
            reply = ask_llm("Problem:\n%s\n\nOutput:\n%s\n\nCode you may change:\n%s" % (problem, out[-3000:], ctx or "(no file excerpt available)"), SYSTEM)
        except Exception as e:
            report.append("AI patch skipped: the AI request failed (%s)." % type(e).__name__); return False
        if reply is None:
            report.append("AI patch skipped: no API key configured."); return False
        if "NO_SAFE_FIX" in reply:
            report.append("AI attempt %d: no safe fix proposed." % attempt); continue
        status, detail, paths, lines = apply_change(reply, g, max_lines=g["max_diff_lines"])
        if status in ("protected", "too_big", "not_allowed"):
            report.append("AI attempt %d REJECTED by guardrails (%s: %s)." % (attempt, status, detail)); continue
        if status != "ok":
            report.append("AI attempt %d: %s." % (attempt, detail)); continue
        run(cfg()["commands"].get("post_patch", ""))        # e.g. rebuild index.html from source/
        rc, o = run(cfg()["commands"]["test"])
        if rc == 0:
            report.append("AI attempt %d: change applied (%d files, %d lines); tests now pass." % (attempt, len(paths), lines)); return True
        git("checkout", "--", "."); report.append("AI attempt %d: change applied but tests still failing; reverted." % attempt); out = o
    return False

def main():
    load_env(); ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["weekly", "feedback", "test-notify", "test-ai"]); ap.add_argument("--text", default="")
    ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    if a.mode == "test-ai":
        import urllib.error
        try:
            reply = ask_llm("Reply with exactly the word: OK", "You are a connectivity check.")
        except urllib.error.HTTPError as e:
            print("AI check FAILED: OpenAI answered HTTP %d. %s" % (e.code, {401: "The key was rejected (wrong, revoked or mistyped).", 429: "Rate limit or no credit on the account.", 404: "Model name not available; check AGENT_MODEL."}.get(e.code, ""))); return 1
        except Exception as e:
            print("AI check FAILED: could not reach OpenAI (%s). Check your internet connection." % type(e).__name__); return 1
        if reply is None:
            print("AI check FAILED: no key found. Put OPENAI_API_KEY in ai-maintenance/.env (not .env.example)."); return 1
        print("AI check OK: the key works and the model answered. The agent can now write fixes."); return 0
    if a.mode == "test-notify":
        notify("This is a test. If you can read this, desktop notifications work.\nThe agent will show one like it when it changes or needs something.", title="Beer Game maintenance (test)")
        print("Test notification sent. Look at the bottom-right of your screen / Notification centre (and Telegram, if set up).")
        return 0
    c = cfg(); g = c["guardrails"]; gb = c["git"]
    ready = subprocess.run(["git", "rev-parse", "--verify", "-q", gb["dev_branch"]], cwd=REPO, capture_output=True).returncode == 0 \
        and subprocess.run(["git", "rev-parse", "--verify", "-q", gb["test_branch"]], cwd=REPO, capture_output=True).returncode == 0
    if not ready:
        sys.exit("This folder is not set up as a git repository with dev / test / %s branches yet.\nRun this once:  python ai-maintenance/agent/setup_repo.py" % gb["live_branch"])
    lock = os.path.join(STATE, "lock"); os.makedirs(STATE, exist_ok=True)
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 3 * 3600:
        sys.exit("Another maintenance run is in progress (state/lock). A lock older than 3 hours is treated as stale.")
    open(lock, "w").write(now())
    report = ["# %s run (%s)" % (a.mode, now()), ""]
    try:
        if dirty():
            raise RuntimeError("Repo has uncommitted changes; refusing to run. Changed: " + ", ".join(l.strip() for l in dirty().splitlines()[:8]))
        git("checkout", gb["dev_branch"])
        work = "ai/%s-%s" % (a.mode, now()); git("checkout", "-b", work)
        if a.mode == "feedback":
            report.append("Feedback received: " + a.text)
        run(c["commands"]["install"])
        for t in c["maintenance_tasks"]:
            if a.mode == "weekly" and t["cmd"]:
                rc, o = run(t["cmd"]); report.append("task %s: %s" % (t["name"], "ok" if rc == 0 else "FAILED"))
        rc, out = run(c["commands"]["test"])
        problem = None
        if rc != 0:
            problem = "Tests are failing after maintenance tasks."
        elif a.mode == "feedback":
            problem = "A user reported: " + a.text
        fixed_by_ai = False
        if problem:
            report.append("Problem: " + problem)
            fixed_by_ai = try_patch(problem + ("\nUser report: " + a.text if a.text else ""), out, g, report)
            rc2, _ = run(c["commands"]["test"])
            if rc2 != 0:
                report.append("RESULT: could not get to green. Nothing was promoted. Human attention needed.")
                git("checkout", "--", "."); git("checkout", gb["dev_branch"]); git("branch", "-D", work)
                p = write_report(a.mode, report); notify("\n".join(report)); return 1
        suggestions, applied = [], []
        if a.mode == "weekly":
            if dirty():                                     # keep upkeep changes separate from AI proposals
                git("add", "-A", "--", ".", ":!ai-maintenance"); git("commit", "-q", "-m", "AI weekly: upkeep")
            applied, suggestions = review.review(report)
        ahead = int(git("rev-list", "--count", "%s..%s" % (gb["dev_branch"], work)) or 0)
        if not dirty() and ahead == 0:
            report.append("RESULT: nothing to change; portal is healthy."); git("checkout", gb["dev_branch"]); git("branch", "-D", work)
            write_report(a.mode, report); notify("\n".join(report), desktop=bool(suggestions), toast=toast_for([], suggestions, True, [], False)); return 0
        nfiles = len(set(git("diff", "--name-only", gb["dev_branch"]).splitlines()) | {l[3:] for l in dirty().splitlines()})
        if nfiles > g["max_changed_files"]:
            report.append("RESULT: %d files changed, above the limit of %d. Stopped." % (nfiles, g["max_changed_files"]))
            git("checkout", "--", "."); git("clean", "-fd", "--", ".", ":!ai-maintenance"); git("checkout", gb["dev_branch"]); git("branch", "-D", work)
            write_report(a.mode, report); notify("\n".join(report)); return 1
        if dirty():
            git("add", "-A", "--", ".", ":!ai-maintenance"); git("commit", "-m", "AI %s: %s" % (a.mode, (a.text or "upkeep")[:60]))
        ok, lines = pipeline.promote(work, dry=a.dry_run)
        report += lines + ["RESULT: " + ("promoted" if ok else "FAILED, rolled back")]
        write_report(a.mode, report); notify("\n".join(report), toast=toast_for(applied, suggestions, ok, lines, fixed_by_ai)); return 0 if ok else 1
    except Exception as e:
        report.append("ERROR: %s" % e); write_report(a.mode, report); notify("\n".join(report)); return 2
    finally:
        try: os.remove(lock)
        except OSError: pass

if __name__ == "__main__":
    sys.exit(main())
