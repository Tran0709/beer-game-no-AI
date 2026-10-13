# Beer Game: Weekly AI Self-Maintenance (standard build)

An agent that looks after the game every week: it checks the game is healthy, fixes what it can, proves the fix in a safe copy, and only then asks you to approve it going live. Python standard library + Node, no installs.

## The loop
```
 Monday 02:00 SGT (GitHub Action) ─┐        ┌─ Telegram: "retailer can't see orders"
                                   ▼        ▼   /status /run /approve /rollback
                      ai-maintenance/agent/maintain.py
   branch off dev → rebuild index.html from source/ → run the health suite (tests/run_all.js)
   red? → ask OpenAI for a small patch → guardrails → rebuild → re-test
        ▼
   DEV   tests + smoke
   TEST  = DIGITAL TWIN (scripts/make_twin.js): the live bundle wired to a sandbox relay (`relay-server/`, `ws://localhost:8787`),
           proven identical to live except the relay URL. Real players are never touched.
        ▼
   LIVE gate → you reply /approve in Telegram  → main updated, restore tag made
        ▼  a failing live check rolls back automatically; /rollback does it by hand
```

## What the weekly health check covers (`node tests/run_all.js`)
Sources and the relay server parse · `index.html` matches `source/` · key screens present · no API key or `.env` anywhere in the project · 150 bot-only games stay sane (no NaN/negative stock, cost, backlog) · Facilitator order ceiling enforced · twin builds and matches live.

## The digital twin
`start-twin.bat` (or `node scripts/run_twin.js`) starts a private replica at http://localhost:8080: the exact live game, wired to the real relay server running on your own machine. Open it in several tabs to play a full multiplayer game with no risk to real players. Every time a change reaches the TEST stage, `scripts/twin_selfcheck.js` boots the twin and confirms the page is served and the relay accepts connections.

## Proactive review (the AI thinks of changes)
Every weekly run, after the health check, the AI reviews the project and looks for things worth improving (fragile code, missing error handling, wrong docs, risky settings). It is told not to invent work: if nothing is worth changing it says so and stays quiet.
- **Small, safe ideas** in the files it may touch on its own (`proactive.allowed_prefixes` in `config/config.json`) are applied on a work branch and kept only if every test still passes. They then go dev → test (twin) → your approval, like any other change.
- **Bigger ideas**, or anything in the game rules, UI, tests or config, are never changed automatically. They are written to the weekly report and shown in your notification as "Suggestion for a human".
- Limits: at most 2 proposals and 30 changed lines each per week. Turn it off with `"proactive": {"enabled": false}`.
- What is sent to OpenAI: the text of the allowed small files, the file list, and recent reports/feedback. Never `.env` or other secrets.

## Check the AI connection
`python ai-maintenance/agent/maintain.py test-ai` sends one tiny request to OpenAI and says whether your key works (it never prints the key).

## Desktop notifications
Whenever the agent changes something, promotes a fix, needs your approval, goes live, rolls back, or can't fix a problem, it pops a notification on the desktop of the machine it runs on (Windows, macOS, Linux), and also messages Telegram if that's set up. A healthy week with nothing to change stays silent on the desktop. Check it works any time with `python ai-maintenance/agent/maintain.py test-notify`. Turn it off with `"desktop_notifications": false` in `config/config.json`.
A desktop pop-up only appears if the agent runs on YOUR computer. The GitHub Action runs in the cloud, so it can only reach you via Telegram. To get desktop pop-ups, run `install-weekly-task.bat` (Windows) once: it schedules the agent on your own PC every Monday 10:00 (the PC must be on).

## Guardrails
The agent can never edit: `.env` files, `tests/` (so it can't "pass" by weakening the tests), `.github/`, or `ai-maintenance/`. Max 12 files / 400 changed lines per run. It never pushes to live without `/approve` (config `approval.live`; `"auto"` is available later). If it can't reach green, nothing is promoted and you are told.

## Setup
0. First time only: double-click `setup-repo.bat` (or run `python ai-maintenance/agent/setup_repo.py`). It turns the folder into a git repo with the `dev`, `test` and `main` environments. Safe to run again.
1. Make the repo's branches: `dev`, `test`, `main` (= live). Copy this folder's contents into it.
2. `ai-maintenance/.env` (from `.env.example`): add your `OPENAI_API_KEY` (only the maintenance agent uses it; the game has no AI feature) and the Telegram bot token (from @BotFather) and your chat ID. Never commit, paste or screenshot it.
3. Telegram: `python ai-maintenance/agent/telegram_bot.py` on any machine that stays on.
4. Weekly schedule: `.github/workflows/weekly-maintenance.yml` (add repo secrets `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`; set `git.push` to `true` in `config/config.json`). Or cron: `0 2 * * 1 python ai-maintenance/agent/maintain.py weekly`.
5. Live deploy: Cloudflare builds this repo from GitHub, so pushing `main` IS the deploy. Set `git.push` to `true` and `/approve` becomes the release button (dev and test pushes can serve as preview builds if Cloudflare preview builds are on). `.assetsignore` keeps everything except the game page off the public website.

## Prove it works (no keys, no network)
`python ai-maintenance/tests/test_framework.py` copies the real game, plants a bug in the engine, and shows the agent healing it through dev → test → approval → live, refusing to touch tests/secrets, and leaving a healthy game alone.

