"""Shared helpers. Python standard library only."""
import json, os, subprocess, sys, datetime, urllib.request, urllib.parse, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)                                   # ai-maintenance/
REPO = os.environ.get("PORTAL_REPO") or os.path.dirname(FW)   # portal repo root
STATE = os.environ.get("AGENT_STATE_DIR") or os.path.join(FW, "state")
REPORTS = os.environ.get("AGENT_REPORTS_DIR") or os.path.join(FW, "reports")

def load_env():
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

def notify(text, desktop=True, title="Beer Game maintenance"):
    """Message every allowed Telegram chat AND (if desktop=True) pop a desktop notification. Never raises."""
    print("[notify] " + text)
    c = cfg()
    if desktop and c.get("desktop_notifications", True):
        body = " ".join(l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#"))
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
