"""Shared helpers. Python standard library only."""
import json, os, re, subprocess, sys, datetime, urllib.request, urllib.parse, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)                                   # ai-maintenance/
REPO = os.environ.get("PORTAL_REPO") or os.path.dirname(FW)   # portal repo root
STATE = os.environ.get("AGENT_STATE_DIR") or os.path.join(FW, "state")
REPORTS = os.environ.get("AGENT_REPORTS_DIR") or os.path.join(FW, "reports")

def load_env():
    if os.environ.get("AGENT_ENV_OFF"):      # tests: never read the real .env
        return
    # ai-maintenance/.env first, then the game's own ai-proxy-server/.env (so one OpenAI key serves both)
    for p in (os.path.join(FW, ".env"), os.path.join(REPO, "ai-proxy-server", ".env")):
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if v.strip():
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def cfg():
    return json.load(open(os.environ.get("AGENT_CONFIG") or os.path.join(FW, "config", "config.json"), encoding="utf-8"))

def run(cmd, cwd=None, timeout=1800):
    """Run a shell command; returns (returncode, combined output)."""
    if not cmd:
        return 0, ""
    p = subprocess.run(cmd, shell=True, cwd=cwd or REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return p.returncode, (p.stdout or "") + (p.stderr or "")

def git(*args, check=True):
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), (p.stderr or p.stdout).strip()))
    return (p.stdout or "").strip()

def now():
    return datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")

def desktop_toast(title, body):
    """Pop a notification on the desktop of the machine the agent runs on. Never raises.
    AGENT_DESKTOP_LOG=<file> writes the toast to a file instead (used by the tests)."""
    log = os.environ.get("AGENT_DESKTOP_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(title + " | " + body.replace("\n", " / ") + "\n")
        return
    env = dict(os.environ, N_TITLE=title, N_BODY=body[:240])
    try:
        if sys.platform == "win32":
            ps = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
                  "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Information; "
                  "$n.Visible = $true; $n.ShowBalloonTip(15000, $env:N_TITLE, $env:N_BODY, 'Info'); Start-Sleep -Seconds 16; $n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", 'display notification (system attribute "N_BODY") with title (system attribute "N_TITLE")'],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["notify-send", title, body[:240]], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print("[notify] desktop notification failed:", e)

def notify(text, desktop=True, title="Beer Game maintenance", toast=None):
    """Message every allowed Telegram chat AND (if desktop=True) pop a desktop notification. Never raises."""
    print("[notify] " + text)
    c = cfg()
    if desktop and c.get("desktop_notifications", True):
        lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
        lead = [l for l in lines if l.startswith(("RESULT", "ERROR", "Problem"))]
        body = toast or " ".join(lead or lines)
        desktop_toast(title, body)
    c = c["telegram"]
    token, ids = os.environ.get(c["token_env"]), os.environ.get(c["allowed_chat_ids_env"], "")
    if not token:
        return
    for cid in [i.strip() for i in ids.split(",") if i.strip()]:
        try:
            tg_call(token, "sendMessage", {"chat_id": cid, "text": text[:3900]})
        except Exception as e:
            print("[notify] telegram failed:", e)

def tg_call(token, method, params, timeout=40):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen("https://api.telegram.org/bot%s/%s" % (token, method), data, timeout=timeout) as r:
        return json.load(r)

def ask_llm(prompt, system):
    """Return the model's text. AGENT_FAKE_LLM=<file> is used by the automated tests."""
    fake = os.environ.get("AGENT_FAKE_LLM")
    if fake:
        return open(fake, encoding="utf-8", newline="").read()
    c = cfg()["llm"]
    key = os.environ.get(c["api_key_env"])
    if not key:
        return None
    model = os.environ.get(c["model_env"]) or c["default_model"]
    if c.get("provider", "openai") == "openai":
        body = json.dumps({"model": model, "temperature": 0,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", body,
            {"Authorization": "Bearer " + key, "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    body = json.dumps({"model": model, "max_tokens": 4000, "system": system,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body,
        {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return "".join(b.get("text", "") for b in json.load(r)["content"])

def patch_paths(patch):
    out = []
    for l in patch.splitlines():
        if l.startswith("+++ ") and not l.startswith("+++ /dev/null"):
            out.append(l[4:].strip().split("\t")[0].removeprefix("b/"))
    return out

def is_protected(path, g):
    if os.path.basename(path).startswith(".env"):
        return True
    return any(path == p.rstrip("/") or path.startswith(p if p.endswith("/") else p + "/") or path == p
               for p in g["protected_paths"])

def write_report(name, lines):
    os.makedirs(REPORTS, exist_ok=True)
    p = os.path.join(REPORTS, "%s-%s.md" % (now(), name))
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return p


# ---------- turning an AI reply into a change ----------
# Preferred format (robust, no line numbers to get wrong):
#   EDIT: path/to/file
#   <<<<<<< FIND
#   exact existing text (must appear exactly once)
#   =======
#   replacement text
#   >>>>>>> REPLACE
# A classic unified diff is still accepted.
EDIT_RE = re.compile(r"EDIT:[ \t]*(\S+)[ \t]*\r?\n<<<<<<< FIND\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n?>>>>>>> REPLACE", re.S)
EDIT_FORMAT_HELP = ("Describe each change as one or more blocks, exactly:\nEDIT: <path relative to repo root>\n<<<<<<< FIND\n<existing text, copied EXACTLY from the file shown; it must appear once>\n"
                    "=======\n<replacement text>\n>>>>>>> REPLACE\nKeep FIND short but unique (a few lines). Do not invent new files.")

def clean_reply(text):
    return "\n".join(l for l in (text or "").strip().splitlines() if not l.startswith("```")).strip()

def apply_change(text, g, allow=None, max_lines=400):
    """Apply an AI-proposed change to the working tree.
    Returns (status, detail, paths, changed_lines); status is ok | already_done | empty | protected | not_allowed | too_big | no_apply."""
    text = clean_reply(text)
    edits = EDIT_RE.findall(text)
    if edits:
        tracked = set(git("ls-files").splitlines()); new = {}; lines = 0; skipped = 0
        for path, find, rep in edits:
            path = path.strip("`'\"")
            if path.startswith("/") or ".." in path.replace("\\", "/").split("/") or path not in tracked:
                return "no_apply", "unknown file " + path, [path], 0
            if is_protected(path, g): return "protected", path, [path], 0
            if allow is not None and path not in allow: return "not_allowed", path, [path], 0
            if path not in new:
                raw = open(os.path.join(REPO, path), encoding="utf-8", newline="").read()
                new[path] = [raw.replace("\r\n", "\n"), "\r\n" in raw]
            f_n, r_n = find.replace("\r\n", "\n"), rep.replace("\r\n", "\n")
            n_found = new[path][0].count(f_n) if f_n.strip() else 0
            if n_found == 0 and len(r_n.strip()) >= 20 and r_n in new[path][0]:   # long enough to be a real match, not a stray "x"
                skipped += 1; continue          # the change is already in the file
            if n_found != 1:
                return "no_apply", "the text to replace was not found exactly once in " + path, [path], 0
            new[path][0] = new[path][0].replace(f_n, r_n, 1)
            lines += max(f_n.count("\n") + 1, (r_n.count("\n") + 1) if r_n else 0)
        if skipped == len(edits):
            return "already_done", "that change is already in place", [], 0
        paths = sorted(new)
        if len(paths) > g["max_changed_files"] or lines > max_lines: return "too_big", "%d files, %d lines" % (len(paths), lines), paths, lines
        for path, (content, crlf) in new.items():
            with open(os.path.join(REPO, path), "w", encoding="utf-8", newline="") as f:
                f.write(content.replace("\n", "\r\n") if crlf else content)
        return "ok", "", paths, lines
    if "+++ " not in text:
        return "empty", "no change proposed", [], 0
    paths = patch_paths(text)
    lines = sum(1 for l in text.splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---"))
    for pth in paths:
        if is_protected(pth, g): return "protected", pth, paths, lines
        if allow is not None and pth not in allow: return "not_allowed", pth, paths, lines
    if not paths or len(paths) > g["max_changed_files"] or lines > max_lines: return "too_big", "%d files, %d lines" % (len(paths), lines), paths, lines
    os.makedirs(STATE, exist_ok=True); pf = os.path.join(STATE, "change.diff")
    with open(pf, "w", encoding="utf-8", newline="\n") as f: f.write(text.replace("\r\n", "\n") + "\n")
    if subprocess.run(["git", "apply", "--ignore-whitespace", pf], cwd=REPO, capture_output=True).returncode != 0:
        return "no_apply", "the patch did not apply", paths, lines
    return "ok", "", paths, lines

STOP = set("the and for that with this have from they when what were been will into your page does not but are can its has was all any".split())

def file_context(text, ask=None, limit=30000):
    """Show the AI the code it needs: files named in `text` (e.g. a failing test's output), or, if none is named,
    the files it picks, as windows around lines that match the problem's keywords."""
    tracked = git("ls-files").splitlines()
    named = [f for f in tracked if f in text or os.path.basename(f) in text]
    if not named and ask:
        reply = ask("Which of these files would you need to read to deal with the problem below? Reply with up to 3 paths, one per line, nothing else.\n\nProblem:\n" + text[:2000] + "\n\nFiles:\n" + "\n".join(tracked))
        picked = set(re.findall(r"[\w./-]+", reply or ""))
        named = [f for f in tracked if f in picked][:3]
    words = [w for w in set(re.findall(r"[a-z]{5,}", text.lower())) if w not in STOP]
    parts, used = [], 0
    for f in named:
        try: lines = open(os.path.join(REPO, f), encoding="utf-8", newline="").read().replace("\r\n", "\n").split("\n")
        except (OSError, UnicodeDecodeError): continue
        focus = [int(n) for n in re.findall(re.escape(os.path.basename(f)) + r":(\d+)", text)]
        if not focus and sum(len(l) + 1 for l in lines) > limit // 2:
            scored = sorted(range(len(lines)), key=lambda i: -sum(w in lines[i].lower() for w in words))
            focus = [i + 1 for i in scored[:4] if any(w in lines[i].lower() for w in words)]
        if focus:
            keep = sorted({j for n in focus for j in range(max(0, n - 30), min(len(lines), n + 30))})
            body = "\n".join(lines[j] for j in keep)
        else:
            body = "\n".join(lines)
        body = body[: max(0, limit - used)]
        used += len(body); parts.append("##### %s (excerpt)\n%s" % (f, body))
    return "\n\n".join(parts)
