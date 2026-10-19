# The Beer Game (LA4) - Supply Chain Simulation

A digital build of the MIT Beer Distribution Game: 5 roles (Retailer,
Wholesaler, Distributor, Manufacturer, Facilitator), 8 weeks by default,
hidden information between roles, and the bullwhip effect as the core
lesson.

This is the standard build - no AI chatbox, no external API dependency.
If you're looking for the version with the AI-powered suggestion feature,
that's a separate package.

## What's in this folder

```
index.html          <- the game itself. Open this file, that's it.
source/               <- the same code, split into readable files
  engine.js              game rules, cost calculations, the AI ordering policy
  market.js              Market Scenarios, the Global/Local news bank
  multiplayer.js         WebSocket/BroadcastChannel connection handling
  ui.js                  every screen, panel and interaction
  base-style.css          all visual styling
relay-server/          <- optional: lets rooms work across different devices
  server.js
  package.json
selenium-tests/        <- automated & visible Selenium test scripts
  README.md              explains which script to use for what
```

## Just want to play?

Open `index.html` in any modern browser. No installation, no server, no
internet needed. Solo mode and same-device multiplayer both work
immediately.

## Two fixes in this build worth knowing about

**A Solo-mode Facilitator bug, now fixed.** Previously, a human playing
Facilitator in Solo mode saw the wrong screen during weeks 1-2 - the full
manual demand-entry field instead of the "fixed at 4 units, confirm"
screen the exercise calls for. If they didn't think to type 4 themselves,
that week's demand silently recorded as 0 instead of 4. Verified fixed:
weeks 1-2 now correctly show the Confirm screen and record demand of 4
each, tested directly against the running engine.

**A multiplayer connection leak, now fixed.** Retrying a host or join
attempt after a stuck or failed connection used to leave the *previous*
attempt's retry loop running in the background indefinitely, with nothing
left able to cancel it - completely invisible, and it would keep firing
even after switching to an unrelated game. Fixed by explicitly closing any
existing connection before starting a new one. Verified directly: the old
connection's retry counter now stays frozen the moment it's replaced,
rather than continuing to climb.

## Current feature state

Several features are built and tested but shipped switched off, each
behind its own flag near the top of `source/ui.js` or `source/market.js`
(`SHOW_...`), so any of them can be turned on or off in one line without
rebuilding logic:

- **AI Ordering Review** (`SHOW_AI_ORDERING_REVIEW`) - flags ordering
  mistakes per role, per week, for the Facilitator only. Off pending
  sign-off on the idea itself.
- **Facilitator live screen** (`SHOW_FACILITATOR_LIVE_SCREEN`) - a
  reconstructed view of a followed role's screen. Off; noted as a possible
  future extension.
- **Decision Timer** (`SHOW_DECISION_TIMER`) - on.
- **Starting Price**, **Base Supply** per scenario - off; neither is part
  of the LA4 documentation and Base Supply has no mechanical effect in the
  engine regardless of its setting.
- **Market chart** (`SHOW_MARKET_CHART`, in `market.js`) - off per
  request; the underlying Alpha Vantage integration still exists.
- **Backlog vibration alert** - on. Fires sound, screen shake, and (on
  supported devices) vibration when a role's backlog rises above zero.

## Still open

- **14-can demand limit.** The documentation says the End Consumer never
  orders more than 14 cans a week. Not enforced anywhere currently - a
  Facilitator can enter any number.
- **Submission order.** Roles submit in sequence (Facilitator, then
  Retailer, Wholesaler, Distributor, Manufacturer) rather than
  simultaneously as the documentation states. Each role is shown the order
  its buyer placed that week as soon as the buyer has submitted - the
  Retailer sees the Facilitator's demand, the Wholesaler sees the
  Retailer's order, and so on, with any news adjustment already included -
  so a role now decides knowing this week's incoming order. Bots still
  ignore everything from the current week, and every order is still locked
  in before any of them is applied.
  Only the Facilitator also sees how many units each role has just ordered, the
  moment they submit (with any news adjustment spelled out); other players and a
  host who is not the Facilitator do not. A waiting role shows its order from last
  week instead. The Settings menu shows a "Build" line: if it is missing, an older
  copy of the game is being served.

## Help & Guide

Settings (the gear) -> Help & Guide opens a walkthrough video of about a minute
and the written guide. The video has captions (CC button) and 13 chapter buttons
that jump to each step. The video and captions are embedded in `source/ui.js`
(`HOW_TO_PLAY_VIDEO_BASE64`, `HOW_TO_PLAY_CHAPTERS`, `HOW_TO_PLAY_CAPTIONS_VTT`), so
the game stays a single file. It shows the game as it looks today: if the screens or
rules change, the video needs regenerating, or it will go out of date again.

## Facilitator interventions

When one role is stuck in a backlog spiral (a Retailer that understocks, then
panic-orders to clear the backlog and floods everyone upstream), the Facilitator
panel has three levers. All are off until switched on, and the players they affect
are told on their own screens.

- **Information sharing.** Shows the Retailer's stock, backlog and the real customer
  demand to the Wholesaler or to the whole chain. AI seats in that scope also order
  from real customer demand instead of the order their buyer placed. This
  deliberately breaks the normal rule that you only see your own numbers.
- **Order ceiling.** Caps one role's weekly order for a number of weeks, counted
  from the current week. Applied after any news adjustment, to humans and AI alike.
  A player who types more is told, and the next role is shown the capped number.
- **Market shift.** Different stock and/or backlog cost for one role or all of
  them, from the next week resolved. Past weeks are never recalculated, the
  end-of-game baseline is charged the same changed rates, and the results screen
  says when costs were changed because totals are then not directly comparable.
  The panel warns when backlog would cost less than stock: that makes running
  short the cheaper strategy.

`analysis/intervention-scenario.js` reproduces the comparison below with the real
engine (`node analysis/intervention-scenario.js`). A Retailer that understocks for
four weeks and then panic-orders, 16-week game, customers ordering 8 a week,
interventions switched on at week 7:

| Scenario | Chain cost | Retailer | Upstream |
|---|---|---|---|
| Healthy chain (all AI) | $742 | $114 | $628 |
| The problem, no intervention | $17,414 | $512 | $16,902 |
| Information sharing, whole chain | $10,216 | $440 | $9,776 |
| Information sharing, Wholesaler only | $11,676 | $488 | $11,188 |
| Order ceiling 12 for 4 weeks | $8,520 | $560 | $7,960 |
| Order ceiling 16 for 3 weeks | $11,160 | $536 | $10,624 |
| Market shift: Retailer backlog $0.50 | $17,084 | $182 | $16,902 |
| Ceiling 12 (4 weeks) plus sharing | $3,933 | $496 | $3,437 |

The Retailer in this run is scripted, so it cannot respond to incentives: the market
shift lowers that Retailer's bill but cannot show the behaviour change it is meant to
cause. Real players may react differently.

## Want multiplayer across different devices?  
To use the relay server, ensure you install the required dependencies by running `npm install` in the `relay-server/` directory, which includes the `ws` package.

By default multiplayer works between browser tabs on the same machine. For
players joining from their own devices with just a room code, the relay
server needs to be running somewhere reachable:

To try the relay on your own computer first (needs Node.js): open a terminal in
`relay-server/`, run `npm install` once (it downloads the one dependency, `ws`),
then `npm start`. It listens on port 8787, so the local address is `ws://localhost:8787`.
(`start-twin.bat` does all of this for you and also serves a private copy of the game.)

1. Deploy `relay-server/` to any Node host (Render, Railway, Fly.io all
   have a free tier). Entry point `server.js`, started with `npm start`.
   If the platform builds from a repository root, set the service's
   **Root Directory** to `relay-server`.
2. Put the resulting `wss://` URL into `DEFAULT_SERVER_URL` in
   `source/multiplayer.js`, then rebuild `index.html` (see below) - or use
   the in-game "Advanced: change the server address" field on the
   Host/Join screens to point a specific room at a different relay without
   rebuilding at all.

**Free-tier note:** these hosts sleep an idle service and take 30-60
seconds to wake. The game sends a wake-up request before connecting and
retries for about a minute, showing "Waking up the game server..." rather
than failing outright.

## Rebuilding index.html from source

`index.html` is the CSS and the four JS files concatenated into one
self-contained file:

```python
engine = open('source/engine.js').read()
market = open('source/market.js').read()
multiplayer = open('source/multiplayer.js').read()
ui = open('source/ui.js').read()
css = open('source/base-style.css').read()

html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Beer Game: Supply Chain Simulation</title>
<style>{css}</style></head>
<body><div id="app"></div><div id="helpModalRoot"></div>
<script>{engine}\n\n{market}\n\n{multiplayer}\n\n{ui}</script>
</body></html>'''

open('index.html', 'w').write(html)
```

## A note on the sound

Music and effects are synthesized in the browser using the Web Audio API,
not audio files. This keeps `index.html` self-contained with no external
assets and no licensing concerns.

## A note on the market chart

The beer-industry stock reference is hidden per request. The Alpha
Vantage integration in `market.js` still exists behind
`SHOW_MARKET_CHART`. Note the API key there is visible in the page source
and shares a rate-limited free quota, so reconsider before enabling it on
a public deployment.
