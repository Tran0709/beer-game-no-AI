"""Proactive weekly review: the AI looks over the project, THINKS of improvements, and applies the small safe ones.
 - small, low-risk changes in allowed files -> applied on the work branch, kept only if every test still passes
 - bigger ideas, or anything in a file it may not touch (game rules, UI, tests) -> written down as SUGGESTIONS for a human
Never changes game rules, scoring, tests, config or secrets."""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *

SYSTEM = ("You are doing the weekly proactive review of The Beer Game, a browser simulation, as its careful maintenance engineer. "
          "Think about what would genuinely make the project more robust, secure, clear or correct: unhandled errors, fragile code, "
          "outdated or wrong documentation, risky settings, missing input checks. Do NOT invent work: if nothing is worth changing reply exactly NO_PROPOSALS. "
          "NEVER change game rules, scoring, costs or engine behaviour, tests, config, or secrets. "
          "Reply with at most {n} proposals, each in exactly this format:\n"
          "=== PROPOSAL ===\nTITLE: <short title>\nWHY: <one or two sentences: the concrete problem and the benefit>\n"
          "PATCH:\n<the change, of at most {lines} changed lines, touching ONLY files shown below. " + EDIT_FORMAT_HELP + ">\n=== END ===\n"
          "If an idea is bigger than that, or concerns a file you were not shown, write PATCH: NONE and explain the idea in WHY so a human can decide.")

def candidates(pcfg):
    out, total = [], 0
    for f in git("ls-files").splitlines():
        if not any(f == p or f.startswith(p) for p in pcfg["allowed_prefixes"]):
            continue
        path = os.path.join(REPO, f)
        try:
            if os.path.getsize(path) > pcfg["max_file_bytes"]:
                continue
            text = open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if total + len(text) > pcfg["max_context_chars"]:
            break
        total += len(text); out.append((f, text))
    return out

def recent_context(limit=3):
    parts = []
    if os.path.isdir(REPORTS):
        for n in sorted(os.listdir(REPORTS))[-limit:]:
            try: parts.append("--- report %s\n%s" % (n, open(os.path.join(REPORTS, n), encoding="utf-8").read()[:1500]))
            except OSError: pass
    fb = os.path.join(STATE, "feedback.jsonl")
    if os.path.exists(fb):
        parts.append("--- recent human feedback\n" + "".join(open(fb, encoding="utf-8").readlines()[-8:]))
    return "\n".join(parts)

def parse(reply):
    if reply is None or "NO_PROPOSALS" in reply and "=== PROPOSAL ===" not in reply:
        return []
    items = []
    for blk in re.findall(r"=== PROPOSAL ===(.*?)=== END ===", reply, re.S):
        t = re.search(r"TITLE:\s*(.+)", blk); w = re.search(r"WHY:\s*(.+?)\nPATCH:", blk, re.S); p = re.search(r"PATCH:\s*\n?(.*)", blk, re.S)
        patch = (p.group(1).strip() if p else "")
        if patch.startswith("```"):
            patch = "\n".join(l for l in patch.splitlines() if not l.startswith("```")).strip()
        items.append({"title": (t.group(1).strip() if t else "untitled"), "why": (w.group(1).strip() if w else ""),
                      "patch": None if (not patch or patch.upper().startswith("NONE")) else patch})
    return items

def review(report):
    """Run the review on the current work branch. Returns (applied_titles, suggestions)."""
    c = cfg(); pcfg = c.get("proactive", {})
    if not pcfg.get("enabled"):
        return [], []
    g = c["guardrails"]; files = candidates(pcfg)
    prompt = "Files you may propose patches for:\n" + "\n".join("##### %s\n%s" % (f, t) for f, t in files) \
             + "\n\nFull list of project files (others may only be mentioned as ideas):\n" + git("ls-files") + "\n\nRecent maintenance history:\n" + recent_context()
    try:
        reply = ask_llm(prompt, SYSTEM.format(n=pcfg["max_proposals"], lines=pcfg["max_lines_per_proposal"]))
    except Exception as e:
        report.append("Proactive review skipped: AI request failed (%s)." % type(e).__name__); return [], []
    if reply is None:
        report.append("Proactive review skipped: no AI key configured."); return [], []
    applied, suggestions = [], []
    items = parse(reply)[: pcfg["max_proposals"]]
    if not items:
        report.append("Proactive review: the AI found nothing worth changing."); return [], []
    allowed_files = {f for f, _ in files}
    for it in items:
        t = it["title"]
        if it["patch"] is None:
            suggestions.append("%s: %s" % (t, it["why"])); continue
        status, detail, paths, lines = apply_change(it["patch"], g, allow=allowed_files, max_lines=pcfg["max_lines_per_proposal"])
        if status != "ok":
            why_not = {"no_apply": "the change did not apply (%s); idea kept for a human" % detail,
                       "empty": "no usable change was given; idea kept for a human"}.get(status, "not auto-applied: outside the files or size the AI may change on its own")
            suggestions.append("%s: %s (%s)" % (t, it["why"], why_not)); continue
        run(c["commands"].get("post_patch", ""))
        rc, _ = run(c["commands"]["test"])
        if rc != 0:
            git("checkout", "--", "."); git("clean", "-fd", "--", ".", ":!ai-maintenance")
            suggestions.append("%s: %s (tried it, but the tests failed, so it was undone)" % (t, it["why"])); continue
        git("add", "-A", "--", ".", ":!ai-maintenance"); git("commit", "-q", "-m", "AI proposal: " + t[:70])
        applied.append("%s: %s" % (t, it["why"]))
    for a in applied: report.append("Proposal APPLIED (tests green): " + a)
    for s in suggestions: report.append("Suggestion for a human: " + s)
    return applied, suggestions
