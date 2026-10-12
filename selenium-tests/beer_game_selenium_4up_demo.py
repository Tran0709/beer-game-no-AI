"""
The Beer Game (LA4) - LIVE VISIBLE DEMO, ALL 4 ROLES AT ONCE, TILED WINDOWS
===============================================================================
Different from beer_game_selenium_live_demo.py, which plays each role in
turn, one at a time, as separate solo games. This version opens 4 REAL
browser windows simultaneously, tiled into quadrants of your screen, all
joined into the SAME multiplayer room - so you're watching one genuine
shared game, not 4 unrelated ones.

Layout:
    +------------------+------------------+
    |     RETAILER      |    WHOLESALER    |
    |    (top-left)      |   (top-right)    |
    +------------------+------------------+
    |    DISTRIBUTOR     |   MANUFACTURER   |
    |   (bottom-left)     |  (bottom-right)  |
    +------------------+------------------+

The Facilitator seat is deliberately left EMPTY. The game already treats an
unseated Facilitator as "auto-driven" - it generates a real demand number
itself each week (the same auto-demand logic used everywhere else in the
game with no human facilitator) and never blocks the chain waiting on
someone who isn't there. That's a genuine, tested behaviour of the game
itself, not a workaround built for this script - which means this demo
only needs exactly 4 windows for exactly 4 roles, nothing extra.

Requirements:
    pip install selenium
    All 4 windows connect through RELAY_SERVER_URL, set near the top of
    this file - currently wss://beer-game-xnnq.onrender.com. This is done
    via the game's own "Advanced: change the server address" field, rather
    than relying on whatever server happens to be baked into the frontend
    build at file_url. That means file_url only needs to be wherever the
    game's HTML is served from; it does not need to already point at this
    relay server itself.

    Usage:
        python beer_game_selenium_4up_demo.py https://your-frontend-url/

If the relay server is asleep (free-tier hosting) the first connection can
take up to a minute - the game's own retry logic handles that, this script
just needs a little patience on the first join.

This is a demo, not an automated test - nothing here asserts pass/fail.
For that, use beer_game_selenium_tests.py.
"""

import sys
import pathlib
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PACE = 1.0

# The relay server every window should connect through. This name follows
# the same "beer-game-XXXX.onrender.com" pattern as the relay used
# elsewhere in this project - visiting it directly in a browser should show
# plain text "relay ok", not the game itself. If that's not what you see at
# this address, this isn't a relay server URL and this script needs a
# different value here.
RELAY_SERVER_URL = "wss://beer-game-xnnq.onrender.com"

# (role_key, label, window quadrant). The first entry HOSTS the room; the
# other three JOIN it. Facilitator is intentionally not in this list - see
# the module docstring for why that's fine.
ROLES = [
    ("retailer", "🏪 Retailer", "top-left"),
    ("wholesaler", "🏬 Wholesaler", "top-right"),
    ("distributor", "🚚 Distributor", "bottom-left"),
    ("manufacturer", "🏭 Manufacturer", "bottom-right"),
]

ORDER_SEQUENCE = [7, 9]  # two real decision weeks, after the 2 fixed ones
GAME_WEEKS = 4


def say(label, msg):
    print(f"\n>>> [{label}] {msg}")


def new_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def position_window(driver, quadrant, screen_w=1920, screen_h=1080):
    """Tiles this window into one quarter of a (assumed) 1920x1080 screen.
    Adjust screen_w/screen_h at the top of this function if your monitor
    is a different resolution - Selenium can't detect that automatically."""
    w, h = screen_w // 2, screen_h // 2
    x = 0 if "left" in quadrant else w
    y = 0 if "top" in quadrant else h
    driver.set_window_rect(x=x, y=y, width=w, height=h)


def wait_click(driver, by, value, timeout=10):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    el.click()
    return el


def wait_present(driver, by, value, timeout=10):
    el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    return el


def type_into(driver, by, value, text, timeout=10):
    """Types character by character for a visible, human-looking effect.
    ChromeDriver's send_keys() cannot handle characters outside the Basic
    Multilingual Plane (BMP) - that includes most emoji, which live above
    U+FFFF - and throws a WebDriverException the instant it hits one. This
    strips anything send_keys() can't handle before typing, so a stray
    emoji anywhere in a string passed to this function can't crash the
    whole run. It warns when it does so, rather than silently typing
    something different from what was asked for.
    """
    text = str(text)
    safe_text = "".join(ch for ch in text if ord(ch) <= 0xFFFF)
    if safe_text != text:
        print(f"   (note: stripped non-BMP characters before typing - "
              f"ChromeDriver can't send_keys() emoji. Typed: {safe_text!r})")
    el = wait_present(driver, by, value, timeout)
    el.clear()
    for ch in safe_text:
        el.send_keys(ch)
        time.sleep(0.08)


def set_server_url(driver, toggle_id, input_id, server_url):
    """Expands the Advanced section and sets an explicit relay server,
    rather than trusting whatever DEFAULT_SERVER_URL happens to be baked
    into this particular frontend build."""
    wait_click(driver, By.ID, toggle_id)
    time.sleep(0.3)
    type_into(driver, By.ID, input_id, server_url)


def host_setup_and_get_code(driver, file_url, weeks):
    driver.get(file_url)
    wait_click(driver, By.ID, "startBtn")
    time.sleep(0.3)
    wait_click(driver, By.ID, "pickMulti")
    time.sleep(0.3)
    wait_click(driver, By.ID, "pickHost")
    time.sleep(0.4)
    type_into(driver, By.ID, "hostName", "Retailer-Host")
    type_into(driver, By.ID, "hostWeeks", str(weeks))
    set_server_url(driver, "toggleAdvancedHost", "hostServerUrl", RELAY_SERVER_URL)
    wait_click(driver, By.ID, "createRoomBtn")
    time.sleep(1.0)
    code = WebDriverWait(driver, 15).until(
        lambda d: d.execute_script("return window.state && state.lobby && state.lobby.code;")
    )
    return code


def guest_join(driver, file_url, name, room_code):
    driver.get(file_url)
    wait_click(driver, By.ID, "startBtn")
    time.sleep(0.3)
    wait_click(driver, By.ID, "pickMulti")
    time.sleep(0.3)
    wait_click(driver, By.ID, "pickJoin")
    time.sleep(0.4)
    type_into(driver, By.ID, "joinName", name)
    type_into(driver, By.ID, "joinCode", room_code)
    set_server_url(driver, "toggleAdvancedJoin", "joinServerUrl", RELAY_SERVER_URL)
    wait_click(driver, By.ID, "joinRoomBtn")
    time.sleep(1.0)


def claim_seat(driver, role_key, team_index=0):
    sel = f'.seat-cell[data-team="{team_index}"][data-role="{role_key}"]'
    wait_click(driver, By.CSS_SELECTOR, sel)


def is_gated(driver):
    """True if this role's order form is currently locked (waiting on
    someone earlier in the submission order)."""
    return len(driver.find_elements(By.ID, "orderInput")) == 0


def submit_order(driver, label, qty):
    if is_gated(driver):
        say(label, "still waiting for their turn, gate not open yet - skipping this pass")
        return False
    type_into(driver, By.ID, "orderInput", qty)
    time.sleep(0.2)
    wait_click(driver, By.ID, "submitOrderBtn")
    say(label, f"submitted an order of {qty}")
    return True


def normalize_file_url(path):
    """Accepts a plain filesystem path, or a URL/URI already in its final
    form (http://, https://, or file://) and passed through unchanged.
    Without this, passing an already-prefixed file:// URI - which looks
    like exactly the right thing to paste in - gets mistaken for a plain
    path and mangled by pathlib, producing a confusing error that has
    nothing to do with the actual mistake. Also useful here since these
    scripts primarily expect a real http(s) URL (multiplayer needs a real
    relay), but a local file path should still work without crashing."""
    if path.startswith(("http://", "https://", "file://")):
        return path
    return pathlib.Path(path).resolve().as_uri()


def main():
    if len(sys.argv) < 2:
        print("Usage: python beer_game_selenium_4up_demo.py https://your-deployed-url/")
        print("       (or a file:// path / local index.html for same-device testing)")
        sys.exit(1)
    file_url = normalize_file_url(sys.argv[1])

    print("=" * 70)
    print("  THE BEER GAME - 4 ROLES AT ONCE, TILED ACROSS 4 REAL WINDOWS")
    print("  Facilitator seat is left empty - the game auto-drives demand.")
    print("=" * 70)

    drivers = {}
    try:
        # --- window 1: host, claims Retailer ---
        host_key, host_label, host_quad = ROLES[0]
        say(host_label, "opening the room as host...")
        drivers[host_key] = new_driver()
        position_window(drivers[host_key], host_quad)
        code = host_setup_and_get_code(drivers[host_key], file_url, GAME_WEEKS)
        say(host_label, f"room created, code = {code}")
        claim_seat(drivers[host_key], host_key)
        say(host_label, "claimed the Retailer seat")

        # --- windows 2-4: guests, claim the remaining 3 roles ---
        for role_key, label, quad in ROLES[1:]:
            say(label, "joining the room...")
            drivers[role_key] = new_driver()
            position_window(drivers[role_key], quad)
            # A plain-text name for what actually gets typed into the game -
            # deliberately NOT the emoji-decorated `label` used for console
            # narration. See the note on type_into() for why.
            player_name = role_key.capitalize() + "-Player"
            guest_join(drivers[role_key], file_url, player_name, code)
            claim_seat(drivers[role_key], role_key)
            say(label, "seat claimed")
            time.sleep(0.5)

        time.sleep(1.5)
        say(host_label, "starting the game (host-only action)...")
        wait_click(drivers[host_key], By.ID, "startHostedBtn")
        time.sleep(2.0)

        # --- weeks 1-2: fixed, every role just confirms ---
        for week in (1, 2):
            print(f"\n{'='*70}\n  WEEK {week} - fixed at 4 units, every role confirms\n{'='*70}")
            for role_key, label, _ in ROLES:
                d = drivers[role_key]
                try:
                    wait_click(d, By.ID, "submitOrderBtn", timeout=6)
                    say(label, f"confirmed week {week}")
                except TimeoutException:
                    say(label, f"already past week {week} or button not ready - continuing")
                time.sleep(PACE)

        # --- weeks 3+: real decisions, in the actual submission order,
        #     re-checking each role until its gate opens ---
        for i, qty in enumerate(ORDER_SEQUENCE):
            week = 3 + i
            print(f"\n{'='*70}\n  WEEK {week} - real decisions, sequential order\n{'='*70}")
            for role_key, label, _ in ROLES:
                d = drivers[role_key]
                # give the sequential gate a few short tries to open, since
                # each role only unlocks after the one before it submits
                for attempt in range(10):
                    if submit_order(d, label, qty):
                        break
                    time.sleep(0.8)
                time.sleep(PACE)

        print(f"\n{'='*70}\n  Demo complete. Leaving all 4 windows open for 20 seconds.\n{'='*70}")
        time.sleep(20)

    finally:
        for d in drivers.values():
            d.quit()
        print("\n>>> All windows closed. Demo complete.")


if __name__ == "__main__":
    main()
