"""
The Beer Game (LA4) - LIVE VISIBLE DEMO, ALL 4 ROLES
========================================================
Same idea as before - a real, visible Chrome window, moving slowly enough
to watch - but this version cycles through all 4 chain roles one after
another: Retailer, Wholesaler, Distributor, Manufacturer. Each gets its own
short, complete game (fixed weeks -> real decisions -> results screen), so
you can confirm every role's own screen actually works, not just one.

Each role reloads the page fresh rather than trying to navigate back to
the start screen in-game - simpler and more reliable for a demo than
depending on a working "return to menu" flow mid-script.

To keep 4 full playthroughs watchable in one sitting, each game is set to
the game's own minimum length (4 weeks: the 2 fixed weeks the exercise
always requires, plus 2 real decisions) rather than the default 8.

Usage:
    pip install selenium
    python beer_game_selenium_live_demo.py /path/to/index.html
    python beer_game_selenium_live_demo.py https://your-deployed-url/

Nothing here checks pass/fail - it's a demo, not a test. If you want the
automated verification suite instead, use beer_game_selenium_tests.py.
"""

import sys
import time
import pathlib
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# How long to pause after each visible action, in seconds. Bigger = slower
# and easier to follow; smaller = faster but harder to watch.
PACE = 1.3

# The 4 chain roles, in the order the game itself asks them to submit
# (Facilitator is excluded - it drives demand rather than placing an order,
# so it doesn't fit this same "place an order" demo pattern).
ROLES = [
    ("retailer", "🏪 Retailer"),
    ("wholesaler", "🏬 Wholesaler"),
    ("distributor", "🚚 Distributor"),
    ("manufacturer", "🏭 Manufacturer"),
]

# A short, minimum-length game per role: 4 total weeks = 2 fixed (no
# decision needed) + 2 real orders. Two different quantities so you can
# see the input genuinely change, not just repeat the same number.
GAME_WEEKS = 4
ORDER_SEQUENCE = [7, 9]


def say(msg):
    print(f"\n>>> {msg}")
    time.sleep(0.4)


def new_visible_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def load_game(driver, file_url, timeout=15):
    driver.get(file_url)
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, "startBtn")))
    except TimeoutException:
        raise RuntimeError(
            f"The game never rendered at {file_url} within {timeout}s. "
            "Check the path/URL is correct, or - if this is a live deployed "
            "link - that the server has finished waking up."
        )


def click_slowly(driver, element_id, note=None):
    el = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.ID, element_id)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    time.sleep(0.3)
    if note:
        say(note)
    el.click()
    time.sleep(PACE)


def type_slowly(driver, element_id, text, note=None):
    """Types character by character for a visible, human-looking effect.
    ChromeDriver's send_keys() cannot handle characters outside the Basic
    Multilingual Plane (most emoji included) and throws immediately if it
    hits one - this strips anything unsupported before typing, so a stray
    emoji can't crash the run. Currently this script only ever types plain
    numbers, so this shouldn't trigger, but it's cheap insurance if that
    changes later."""
    text = str(text)
    safe_text = "".join(ch for ch in text if ord(ch) <= 0xFFFF)
    if safe_text != text:
        print(f"   (note: stripped non-BMP characters before typing. Typed: {safe_text!r})")
    el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, element_id)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    if note:
        say(note)
    el.clear()
    for ch in safe_text:
        el.send_keys(ch)
        time.sleep(0.15)
    time.sleep(PACE)


def set_weeks_to_play(driver, weeks):
    el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "soloWeeks")))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    say(f"Setting the game length to {weeks} weeks (the minimum), to keep this demo short.")
    el.clear()
    el.send_keys(str(weeks))
    time.sleep(PACE)


def play_one_role(driver, file_url, role_key, role_label):
    print("\n" + "=" * 60)
    print(f"  NOW DEMONSTRATING: {role_label}")
    print("=" * 60)

    say(f"Loading a fresh game to play as {role_label}.")
    load_game(driver, file_url)
    time.sleep(PACE)

    click_slowly(driver, "startBtn", "Clicking Start on the title screen.")
    click_slowly(driver, "pickSolo", "Choosing Solo Practice mode.")
    set_weeks_to_play(driver, GAME_WEEKS)

    say(f"Selecting the {role_label} role.")
    role_card = WebDriverWait(driver, 8).until(
        lambda d: next(c for c in d.find_elements(By.CLASS_NAME, "role-pick-card")
                        if c.get_attribute("data-role") == role_key)
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", role_card)
    time.sleep(0.3)
    role_card.click()
    time.sleep(PACE)

    say("Weeks 1 and 2 are fixed at 4 units per the exercise rules - confirming both.")
    click_slowly(driver, "submitOrderBtn", "Week 1: confirming the fixed 4-unit order.")
    click_slowly(driver, "submitOrderBtn", "Week 2: confirming the fixed 4-unit order.")

    say(f"From week 3 on, {role_label} makes real decisions.")
    for week_offset, qty in enumerate(ORDER_SEQUENCE, start=3):
        type_slowly(driver, "orderInput", qty, f"Week {week_offset}: typing an order of {qty} units.")
        click_slowly(driver, "submitOrderBtn", f"Submitting week {week_offset}'s order.")

    say(f"{role_label}'s game is complete. Holding on the results screen for a moment.")
    time.sleep(3)


def normalize_file_url(path):
    """Accepts a plain filesystem path, or a URL/URI already in its final
    form (http://, https://, or file://) and passed through unchanged.
    Without this, passing an already-prefixed file:// URI - which looks
    like exactly the right thing to paste in - gets mistaken for a plain
    path and mangled by pathlib, producing a confusing "relative path
    can't be expressed as a file URI" error that has nothing to do with
    the actual mistake."""
    if path.startswith(("http://", "https://", "file://")):
        return path
    return pathlib.Path(path).resolve().as_uri()


def main():
    if len(sys.argv) < 2:
        print("Usage: python beer_game_selenium_live_demo.py /path/to/index.html")
        sys.exit(1)
    file_url = normalize_file_url(sys.argv[1])

    print("=" * 60)
    print("  THE BEER GAME - LIVE SELENIUM DEMO, ALL 4 ROLES")
    print("  A real Chrome window is about to open.")
    print("  Watch it, don't touch it - Selenium is driving.")
    print("=" * 60)
    time.sleep(2)

    driver = new_visible_driver()
    try:
        for role_key, role_label in ROLES:
            play_one_role(driver, file_url, role_key, role_label)

        print("\n" + "=" * 60)
        print("  All 4 roles demonstrated successfully.")
        print("=" * 60)
        say("Leaving the final window open for 15 seconds before closing.")
        time.sleep(15)

    finally:
        driver.quit()
        print("\n>>> Browser closed. Demo complete.")


if __name__ == "__main__":
    main()
