"""End-to-end proof on a COPY of the real game: break the engine, let the agent heal it.
No network, no real AI (a canned patch stands in for the model), no real deploys.
    python ai-maintenance/tests/test_framework.py"""
import os, sys, json, shutil, subprocess, tempfile, unittest
FW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(FW)

def sh(cmd, cwd): return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
def wr(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f: f.write(text)

class Heal(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.aux = tempfile.mkdtemp(); d = self.d
        shutil.copytree(PKG, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "twin", "state", "reports", "__pycache__", "node_modules", ".env"))
        sh("git init -q -b main && git config core.autocrlf false && git config user.email a@b.c && git config user.name t && git add -A && git commit -qm good", d)
        eng = d + "/source/engine.js"; src = open(eng, encoding="utf-8", newline="").read().replace("\r\n", "\n")
        needle = "const value = Math.max(0, Math.round(base + noise));"
        self.assertIn(needle, src)
        wr(eng, src.replace(needle, "const value = Math.round(base + noise) * undefined;"))   # the planted bug
        sh("node scripts/rebuild.js && git commit -qam bug && git branch dev && git branch test", d)
        self.patch = self.aux + "/fix.diff"
        wr(self.patch, sh("git diff HEAD~1 HEAD -R -- source/engine.js", d).stdout)
        self.cfgfile = self.aux + "/cfg.json"; wr(self.cfgfile, json.dumps(dict(json.load(open(FW + "/config/config.json", encoding="utf-8")), git=dict(json.load(open(FW + "/config/config.json", encoding="utf-8"))["git"], push=False))))
        self.env = dict(os.environ, PORTAL_REPO=d, AGENT_CONFIG=self.cfgfile, AGENT_STATE_DIR=self.aux + "/state", AGENT_REPORTS_DIR=self.aux + "/reports", AGENT_DESKTOP_LOG=self.aux + "/toasts.log", AGENT_ENV_OFF="1")
        for k in ("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"): self.env.pop(k, None)
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True); shutil.rmtree(self.aux, ignore_errors=True)
    def agent(self, *a, fake=None):
        env = dict(self.env)
        if fake: env["AGENT_FAKE_LLM"] = fake
        return subprocess.run([sys.executable, FW + "/agent/" + a[0]] + list(a[1:]), cwd=self.d, env=env, capture_output=True, text=True)
    def toasts(self):
        p = self.aux + "/toasts.log"
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    def head(self, b): return sh("git rev-parse " + b, self.d).stdout.strip()
    def test_broken_engine_is_healed_through_dev_test_then_live(self):
        live0 = self.head("main")
        self.assertNotEqual(sh("node tests/run_all.js", self.d).returncode, 0, "the planted bug must be detected")
        r = self.agent("maintain.py", "weekly", fake=self.patch); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tests now pass", r.stdout); self.assertIn("waiting for your approval", r.stdout)
        self.assertIn("waiting for your approval", self.toasts(), "a desktop notification must announce the change")
        self.assertEqual(self.head("main"), live0, "live must not move before approval")
        self.assertEqual(sh("git diff dev test", self.d).stdout, "")
        self.assertEqual(sh("git checkout -q test && node tests/run_all.js", self.d).returncode, 0, "test branch must be green")
        self.assertEqual(sh("git checkout -q dev", self.d).returncode, 0)
        r = self.agent("pipeline.py", "go-live"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.toasts().count("Beer Game maintenance"), 2, "go-live must notify too")
        self.assertEqual(self.head("main"), self.head("test"))
        sh("git checkout -q main", self.d); self.assertEqual(sh("node tests/run_all.js", self.d).returncode, 0, "live must be green")
        sh("git checkout -q dev", self.d)
        self.agent("pipeline.py", "rollback"); self.assertEqual(self.head("main"), live0)
    def test_edit_format_heals_the_engine(self):
        reply = self.aux + "/edit.txt"
        wr(reply, "EDIT: source/engine.js\n<<<<<<< FIND\nconst value = Math.round(base + noise) * undefined;\n=======\nconst value = Math.max(0, Math.round(base + noise));\n>>>>>>> REPLACE\n")
        r = self.agent("maintain.py", "weekly", fake=reply); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tests now pass", r.stdout)
        self.assertIn("Math.max(0, Math.round(base + noise))", sh("git show test:source/engine.js", self.d).stdout)
        self.assertIn("ready, waiting for your approval", open(self.aux + "/toasts.log", encoding="utf-8").read(), "the notification must lead with the outcome")
    def test_edit_that_does_not_match_is_rejected_cleanly(self):
        reply = self.aux + "/edit2.txt"
        wr(reply, "EDIT: source/engine.js\n<<<<<<< FIND\nthis text is not in the file\n=======\nx\n>>>>>>> REPLACE\n")
        r = self.agent("maintain.py", "weekly", fake=reply); self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found exactly once", r.stdout); self.assertEqual(self.head("dev"), self.head("main"))
    def test_edit_cannot_touch_protected_files(self):
        reply = self.aux + "/edit3.txt"
        wr(reply, "EDIT: tests/run_all.js\n<<<<<<< FIND\nlet pass = 0, fail = 0;\n=======\nlet pass = 0, fail = 0; process.exit(0);\n>>>>>>> REPLACE\n")
        r = self.agent("maintain.py", "weekly", fake=reply); self.assertIn("REJECTED by guardrails", r.stdout); self.assertEqual(self.head("dev"), self.head("main"))
    def test_ai_may_not_edit_the_tests_or_secrets(self):
        for target in ("tests/run_all.js", "ai-proxy-server/.env"):
            p = self.aux + "/bad.diff"; wr(p, "--- a/%s\n+++ b/%s\n@@ -1,1 +1,1 @@\n-x\n+y\n" % (target, target))
            r = self.agent("maintain.py", "weekly", fake=p); self.assertIn("REJECTED by guardrails", r.stdout)
            self.assertEqual(self.head("dev"), self.head("main"))
    def test_unfixable_problem_alerts_and_changes_nothing(self):
        p = self.aux + "/none.txt"; wr(p, "NO_SAFE_FIX")
        r = self.agent("maintain.py", "weekly", fake=p); self.assertNotEqual(r.returncode, 0)
        self.assertIn("Human attention needed", r.stdout); self.assertIn("Human attention needed", self.toasts()); self.assertEqual(self.head("dev"), self.head("main"))
    def test_healthy_game_is_left_alone(self):
        sh("git apply --index \"%s\" && node scripts/rebuild.js && git commit -qam fixed && git branch -f dev && git branch -f test" % self.patch, self.d)
        r = self.agent("maintain.py", "weekly"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("healthy", r.stdout); self.assertEqual(self.toasts(), "", "a healthy week must not pop a notification")

class TestNotify(unittest.TestCase):
    def test_test_notify_fires_a_toast(self):
        aux = tempfile.mkdtemp()
        try:
            env = dict(os.environ, AGENT_DESKTOP_LOG=aux + "/t.log", AGENT_STATE_DIR=aux + "/s", AGENT_REPORTS_DIR=aux + "/r", AGENT_ENV_OFF="1")
            r = subprocess.run([sys.executable, FW + "/agent/maintain.py", "test-notify"], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("desktop notifications work", open(aux + "/t.log", encoding="utf-8").read())
        finally: shutil.rmtree(aux, ignore_errors=True)

class Review(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.aux = tempfile.mkdtemp(); d = self.d
        shutil.copytree(PKG, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "twin", "state", "reports", "__pycache__", "node_modules", ".env"))
        sh("git init -q -b main && git config core.autocrlf false && git config user.email a@b.c && git config user.name t && git add -A && git commit -qm good && git branch dev && git branch test", d)
        c = json.load(open(FW + "/config/config.json", encoding="utf-8")); c["proactive"]["max_proposals"] = 4; c["git"]["push"] = False
        wr(self.aux + "/cfg.json", json.dumps(c))
        self.env = dict(os.environ, PORTAL_REPO=d, AGENT_CONFIG=self.aux + "/cfg.json", AGENT_STATE_DIR=self.aux + "/s", AGENT_REPORTS_DIR=self.aux + "/r",
                        AGENT_DESKTOP_LOG=self.aux + "/t.log", AGENT_ENV_OFF="1", AGENT_FAKE_LLM=self.aux + "/reply.txt")
        self.env.pop("OPENAI_API_KEY", None)
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True); shutil.rmtree(self.aux, ignore_errors=True)
    def diff_of(self, rel, add):
        p = self.d + "/" + rel; src = open(p, encoding="utf-8", newline="").read()
        wr(p, src.replace("\r\n", "\n") + add); out = sh("git diff -- " + rel, self.d).stdout; sh("git checkout -- " + rel, self.d); return out
    def weekly(self):
        return subprocess.run([sys.executable, FW + "/agent/maintain.py", "weekly"], cwd=self.d, env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    def head(self, b): return sh("git rev-parse " + b, self.d).stdout.strip()
    def test_ai_applies_safe_ideas_and_only_suggests_the_rest(self):
        head = next(l for l in open(PKG + "/README.md", encoding="utf-8").read().splitlines() if l.startswith("## "))
        good = "EDIT: README.md\n<<<<<<< FIND\n%s\n=======\n%s (reviewed weekly)\n>>>>>>> REPLACE" % (head, head)
        bad = self.diff_of("scripts/rebuild.js", "\nTHIS IS NOT VALID JAVASCRIPT (\n")
        rules = self.diff_of("source/engine.js", "\n// tweak\n")
        blk = lambda t, w, p: "=== PROPOSAL ===\nTITLE: %s\nWHY: %s\nPATCH:\n%s\n=== END ===\n" % (t, w, p)
        wr(self.aux + "/reply.txt", blk("Document the weekly review", "README does not mention the review.", good) + blk("Refactor rebuild", "Cleaner.", bad)
           + blk("Tweak the engine", "Faster.", rules) + blk("Split ui.js into modules", "ui.js is very large; consider splitting it.", "NONE"))
        live0 = self.head("main"); r = self.weekly(); out = r.stdout
        self.assertEqual(r.returncode, 0, out + r.stderr)
        self.assertEqual(out.count("Proposal APPLIED"), 1); self.assertEqual(out.count("Suggestion for a human"), 3)
        self.assertIn("tests failed, so it was undone", out); self.assertIn("not auto-applied", out); self.assertIn("Split ui.js", out)
        self.assertIn("(reviewed weekly)", sh("git show test:README.md", self.d).stdout, "the safe idea must reach the test environment")
        self.assertNotIn("NOT VALID", sh("git show test:scripts/rebuild.js", self.d).stdout)
        self.assertEqual(sh("git diff dev test -- source/", self.d).stdout, "", "game source must be untouched")
        self.assertEqual(self.head("main"), live0, "live must not move before approval")
        self.assertIn("waiting for your approval", out)
        self.assertTrue(open(self.aux + "/t.log", encoding="utf-8").read(), "a desktop notification must announce it")
    def test_nothing_worth_changing_stays_quiet(self):
        wr(self.aux + "/reply.txt", "NO_PROPOSALS")
        r = self.weekly(); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("healthy", r.stdout); self.assertIn("nothing worth changing", r.stdout)
        self.assertFalse(os.path.exists(self.aux + "/t.log"), "no pop-up when nothing happened")
    def test_only_ideas_still_notifies_you(self):
        wr(self.aux + "/reply.txt", "=== PROPOSAL ===\nTITLE: Add rate limiting\nWHY: The relay accepts unlimited rooms per IP.\nPATCH:\nNONE\n=== END ===\n")
        r = self.weekly(); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("rate limiting", r.stdout)
        self.assertIn("rate limiting", open(self.aux + "/t.log", encoding="utf-8").read())
        self.assertEqual(self.head("dev"), self.head("main"))

class TestAI(unittest.TestCase):
    def run_agent(self, **extra):
        aux = tempfile.mkdtemp()
        try:
            env = dict(os.environ, AGENT_STATE_DIR=aux + "/s", AGENT_REPORTS_DIR=aux + "/r", **extra); env.pop("OPENAI_API_KEY", None)
            if "AGENT_FAKE_LLM" in extra: wr(extra["AGENT_FAKE_LLM"], "OK")
            return subprocess.run([sys.executable, FW + "/agent/maintain.py", "test-ai"], env=env, capture_output=True, text=True)
        finally: shutil.rmtree(aux, ignore_errors=True)
    def test_ai_check_reports_ok_and_missing_key(self):
        f = tempfile.mktemp(); r = self.run_agent(AGENT_FAKE_LLM=f, AGENT_ENV_OFF="1"); self.assertIn("AI check OK", r.stdout)
        r = self.run_agent(AGENT_ENV_OFF="1"); self.assertIn("no key found", r.stdout)

class Setup(unittest.TestCase):
    def test_plain_folder_gets_set_up_then_runs(self):
        d = tempfile.mkdtemp(); aux = tempfile.mkdtemp()
        try:
            shutil.copytree(PKG, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "twin", "state", "reports", "__pycache__", "node_modules", ".env"))
            env = dict(os.environ, PORTAL_REPO=d, AGENT_STATE_DIR=aux + "/s", AGENT_REPORTS_DIR=aux + "/r", AGENT_DESKTOP_LOG=aux + "/t.log", AGENT_ENV_OFF="1")
            run = lambda *a: subprocess.run([sys.executable, FW + "/agent/" + a[0]] + list(a[1:]), cwd=d, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            r = run("maintain.py", "weekly"); self.assertNotEqual(r.returncode, 0); self.assertIn("setup_repo.py", r.stdout + r.stderr)
            r = run("setup_repo.py"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("Ready", r.stdout)
            self.assertEqual(run("setup_repo.py").returncode, 0, "setup must be safe to repeat")
            branches = sh("git branch", d).stdout; [self.assertIn(b, branches) for b in ("dev", "test", "main")]
            r = run("maintain.py", "weekly"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("healthy", r.stdout)
        finally: shutil.rmtree(d, ignore_errors=True); shutil.rmtree(aux, ignore_errors=True)

if __name__ == "__main__": unittest.main(verbosity=2)
