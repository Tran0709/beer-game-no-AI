# Selenium test scripts - The Beer Game (LA4)

Four scripts, each with a different job. All require:

```bash
pip install selenium
```

You'll also need Chrome and a matching chromedriver on your system PATH.

## Which one do I want?

| Script | What it does | Watch it, or just get a result? |
|---|---|---|
| `beer_game_selenium_tests.py` | Broad coverage across solo mode, the Facilitator, and core game rules | Runs headless - reads the printed pass/fail output |
| `beer_game_selenium_live_demo.py` | Plays through all 5 roles one at a time, slowly, narrated | Visible window - meant to be watched |
| `beer_game_selenium_4up_demo.py` | 4 real browser windows, tiled, one shared multiplayer game | Visible windows - meant to be watched |
| `beer_game_selenium_4role_test.py` | The same 4-window multiplayer setup, but with real pass/fail assertions instead of narration | Visible windows, but check the printed summary at the end for the actual result |

If you want a genuine test with a clear pass/fail outcome for multiplayer, use `beer_game_selenium_4role_test.py`. If you want something to watch - for a demo, a recording, or just to convince yourself it's really working - `beer_game_selenium_4up_demo.py` or `beer_game_selenium_live_demo.py` are built for that instead.

## What you can pass as the URL/path

Any of these work for every script here: a real `http://` or `https://`
URL, an already-formed `file://` URI, or a plain filesystem path (Windows
backslashes included) - the last one gets converted correctly for you. An
earlier version of these scripts only recognized `http`, which meant
pasting in a `file://` URI directly - a completely reasonable thing to
paste - crashed with a confusing "relative path can't be expressed as a
file URI" error. Fixed.

## Running the multiplayer ones

Both 4-window scripts connect through a relay server, set via the
`RELAY_SERVER_URL` constant near the top of each file. By default this
points at the project's Render relay - update it if you're running your
own, or pass a frontend URL for a locally-served build:

```bash
python beer_game_selenium_4role_test.py https://your-frontend-url/
```

`file_url` only needs to be wherever the game's HTML is served from - it
does not need to already point at the relay server, since every window
sets that explicitly via the game's own "Advanced: change the server
address" field.

## A note on `beer_game_selenium_4role_test.py`

This is the newest and most robust of the four - element waits use
`element_to_be_clickable` with an automatic retry on
`ElementNotInteractableException`, typed text is filtered to strip
anything ChromeDriver can't handle (most emoji), and the sequential
submission gate is polled properly rather than assumed to be open the
instant a button first appears. If you only run one of these scripts,
this is the one to reach for.

## What none of these test

None of these scripts touch the AI suggestion chatbox - this package is
the version of the game without that feature. If you need Selenium
coverage that includes the AI chatbox, that lives in the separate
AI-experimental package instead.
