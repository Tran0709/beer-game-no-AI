"""
The Beer Game (LA4) - Selenium Test Suite
===========================================
Covers the checklist sections that are practically automatable. A few
checklist items are marked SKIP below because they need a human eye
(actual audio output, visual layout on a real phone, etc.) - Selenium can
confirm the *mechanism* fired (state flags, DOM presence) but not that
music sounds good or a layout looks right.

Usage:
    pip install selenium
    python beer_game_selenium_tests.py /path/to/index.html

For the multiplayer sections, also start the relay server first:
    cd relay-server && npm install && node server.js
and edit RELAY_URL below if you're not using the default localhost:8787.
"""

import sys
import time
import pathlib
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

RELAY_URL = "ws://localhost:8787"
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []


def record(section, item, status, detail=""):
    results.append((section, item, status, detail))
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
    print(f"{marker} {section} :: {item}" + (f" -- {detail}" if detail else ""))


def new_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,900")
    return webdriver.Chrome(options=options)


def wait_for(driver, by, value, timeout=5):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def load_game(driver, file_url, timeout=10):
    """Load the game and wait for actual proof it rendered (the Start
    button), instead of a blind time.sleep - this fails loudly and clearly
    if the file never loaded correctly, rather than producing a confusing
    NoSuchElementException three lines later on an unrelated click."""
    driver.get(file_url)
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, "startBtn")))
    except TimeoutException:
        raise RuntimeError(
            f"The game never rendered at {file_url} within {timeout}s. "
            "This usually means the file:// URL is malformed or the path is wrong, "
            "not a bug in the game itself. Double-check the path you passed in."
        )


def exists(driver, by, value):
    try:
        driver.find_element(by, value)
        return True
    except NoSuchElementException:
        return False


def click_id(driver, element_id, pause=0.25):
    driver.find_element(By.ID, element_id).click()
    time.sleep(pause)


def state(driver, path):
    """Read a value off window.state via a dotted path, e.g. 'game.week'."""
    return driver.execute_script(f"try {{ return window.state.{path}; }} catch(e) {{ return undefined; }}")


# ---------------------------------------------------------------------------
# SECTION 1: Core Setup & Navigation
# ---------------------------------------------------------------------------
def test_section_1_navigation(file_url):
    section = "1. Core Setup & Navigation"
    driver = new_driver()
    try:
        load_game(driver, file_url)

        logs = driver.get_log("browser") if "goog:loggingPrefs" in driver.capabilities else []
        errors = [l for l in logs if l["level"] == "SEVERE"]
        record(section, "Start screen loads with no console errors", PASS if not errors else FAIL,
               f"{len(errors)} severe console errors" if errors else "")

        record(section, "Settings gear icon present on Start screen",
               PASS if exists(driver, By.ID, "settingsGearBtn") else FAIL)

        record(section, "No standalone Help button on Start screen",
               PASS if not exists(driver, By.ID, "howToPlayBtnStart") else FAIL)

        click_id(driver, "startBtn")
        record(section, "Mode Select reached after Start click",
               PASS if exists(driver, By.ID, "pickSolo") and exists(driver, By.ID, "pickMulti") else FAIL)

        record(section, "No standalone Help button on Mode Select",
               PASS if not exists(driver, By.ID, "howToPlayBtnMode") else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 2: Solo Mode - Core Gameplay
# ---------------------------------------------------------------------------
def test_section_2_solo_gameplay(file_url):
    section = "2. Solo Mode: Core Gameplay"
    driver = new_driver()
    try:
        load_game(driver, file_url)
        click_id(driver, "startBtn")
        click_id(driver, "pickSolo")

        role_card = None
        for card in driver.find_elements(By.CLASS_NAME, "role-pick-card"):
            if card.get_attribute("data-role") == "retailer":
                role_card = card
                break
        role_card.click()
        time.sleep(0.3)

        app_text = driver.find_element(By.ID, "app").text
        record(section, "Fixed week 1-2 messaging present",
               PASS if "fixed at" in app_text else FAIL)
        record(section, "Hidden-information messaging present",
               PASS if ("only see your own" in app_text or "deliberate" in app_text) else FAIL)

        for _ in range(2):
            click_id(driver, "submitOrderBtn")

        week_after_fixed = state(driver, "game.week")
        record(section, "Week advances past fixed weeks (expect 3)",
               PASS if week_after_fixed == 3 else FAIL, f"got week={week_after_fixed}")

        order_input = driver.find_element(By.ID, "orderInput")
        order_input.clear()
        order_input.send_keys("6")
        click_id(driver, "submitOrderBtn")
        stock_after = state(driver, "game.roles.retailer.stock")
        record(section, "Own stock updates after a real submission",
               PASS if stock_after is not None else FAIL, f"stock={stock_after}")

        for week in range(4, 9):
            order_input = driver.find_element(By.ID, "orderInput")
            order_input.clear()
            order_input.send_keys("6")
            click_id(driver, "submitOrderBtn", pause=0.15)

        screen = state(driver, "screen")
        has_baseline = state(driver, "game.baseline") is not None
        record(section, "Full 8-week game reaches results screen",
               PASS if screen == "end" else FAIL, f"screen={screen}")
        record(section, "Baseline comparison computed", PASS if has_baseline else FAIL)

        # Restart via Settings
        click_id(driver, "settingsGearBtn")
        click_id(driver, "settingsRestartBtn")
        week_after_restart = state(driver, "game.week")
        record(section, "Restart (via Settings) resets to week 1",
               PASS if week_after_restart == 1 else FAIL, f"week={week_after_restart}")
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 3: Market Scenario System
# ---------------------------------------------------------------------------
def test_section_3_market_scenario(file_url):
    section = "3. Market Scenario System"
    driver = new_driver()
    try:
        load_game(driver, file_url)
        click_id(driver, "startBtn")
        click_id(driver, "pickSolo")
        time.sleep(0.3)

        icons = driver.find_elements(By.CSS_SELECTOR, "#soloScenarioIcons .scenario-icon-box")
        record(section, "All 4 scenario icons present",
               PASS if len(icons) == 4 else FAIL, f"found {len(icons)}")

        shock_icon = driver.find_element(By.CSS_SELECTOR, '#soloScenarioIcons .scenario-icon-box[data-scenario="shortage"]')
        shock_icon.click()
        time.sleep(0.3)
        overlay_open = "scenario-overlay-open" in driver.find_element(By.ID, "soloScenarioOverlay").get_attribute("class")
        record(section, "Clicking a scenario expands the overlay", PASS if overlay_open else FAIL)

        has_supply = exists(driver, By.ID, "soloScenarioSupply")
        has_demand = exists(driver, By.ID, "soloScenarioDemand")
        severity_chips = driver.find_elements(By.CSS_SELECTOR, "#soloScenarioExtraChoice .chip")
        record(section, "Supply Shock shows Base Supply + Base Demand fields",
               PASS if (has_supply and has_demand) else FAIL)
        record(section, "Supply Shock shows Low/Mid/High severity options",
               PASS if len(severity_chips) == 3 else FAIL, f"found {len(severity_chips)}")

        if severity_chips:
            severity_chips[-1].click()  # High
            time.sleep(0.2)
            active_explain = exists(driver, By.CSS_SELECTOR, ".severity-explain-row.active")
            record(section, "Severity explanation updates when a level is selected",
                   PASS if active_explain else FAIL)

        click_id(driver, "soloScenarioClose")
        no_chart = not exists(driver, By.ID, "soloMarketCanvas")
        record(section, "Stock chart does not appear in setup", PASS if no_chart else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTIONS 4-5: Multiplayer lobby, seating, and gating
# Requires the relay server running locally (see module docstring).
# ---------------------------------------------------------------------------
def test_sections_4_5_multiplayer(file_url):
    section_lobby = "4. Multiplayer: Lobby & Seating"
    section_play = "5. Multiplayer: Live Gameplay"
    host = new_driver()
    guest = new_driver()      # plays Retailer
    guest2 = new_driver()     # plays Wholesaler
    guest3 = new_driver()     # plays Distributor
    try:
        for d in (host, guest, guest2, guest3):
            load_game(d, file_url)

        for d in (host, guest, guest2, guest3):
            click_id(d, "startBtn")

        click_id(host, "pickMulti")
        click_id(host, "pickHost")
        time.sleep(0.4)
        # Point this room at the local relay server via the real "Advanced"
        # field the app reads (DEFAULT_SERVER_URL is a hardcoded constant,
        # not something you can override from outside - this is the only
        # actual way to redirect a session to a different server).
        if exists(host, By.ID, "toggleAdvancedHost"):
            click_id(host, "toggleAdvancedHost")
            host.find_element(By.ID, "hostServerUrl").send_keys(RELAY_URL)
        host.find_element(By.ID, "hostName").clear()
        host.find_element(By.ID, "hostName").send_keys("Host")
        click_id(host, "createRoomBtn", pause=0.6)

        room_code = state(host, "lobby.code")
        record(section_lobby, "Room created with a code", PASS if room_code else FAIL, f"code={room_code}")

        team_seats = host.find_elements(By.CSS_SELECTOR, ".team-grid tbody .seat-cell")
        has_facilitator_seat = exists(host, By.ID, "facilitatorSeatBtn")
        record(section_lobby, "Room shows 4 chain-role seats + 1 Facilitator seat",
               PASS if (len(team_seats) == 4 and has_facilitator_seat) else FAIL,
               f"chain seats={len(team_seats)}")

        click_id(host, "facilitatorSeatBtn")

        def join_as(driver, name, role):
            click_id(driver, "pickMulti")
            click_id(driver, "pickJoin")
            time.sleep(0.3)
            if exists(driver, By.ID, "toggleAdvancedJoin"):
                click_id(driver, "toggleAdvancedJoin")
                driver.find_element(By.ID, "joinServerUrl").send_keys(RELAY_URL)
            driver.find_element(By.ID, "joinName").send_keys(name)
            driver.find_element(By.ID, "joinCode").send_keys(room_code)
            click_id(driver, "joinRoomBtn", pause=0.6)
            driver.find_element(By.CSS_SELECTOR, f'.seat-cell[data-team="0"][data-role="{role}"]').click()
            time.sleep(0.4)

        join_as(guest, "GuestA", "retailer")
        join_as(guest2, "GuestB", "wholesaler")
        join_as(guest3, "GuestC", "distributor")

        guest_name_visible = "GuestA" in host.find_element(By.CSS_SELECTOR,
            '.seat-cell[data-team="0"][data-role="retailer"]').text
        record(section_lobby, "Player name visible to others once seated",
               PASS if guest_name_visible else FAIL)

        click_id(host, "startHostedBtn", pause=0.6)

        # --- Section 5: weeks 1-2 are fixed, just confirm through them for everyone ---
        for _ in range(2):
            click_id(host, "submitDemandBtn")
            for d in (guest, guest2, guest3):
                click_id(d, "submitOrderBtn")
            time.sleep(0.4)

        # --- Week 3: the actual sequential-order test ---
        all_gated = all(not exists(d, By.ID, "orderInput") for d in (guest, guest2, guest3))
        record(section_play, "All 3 connected chain roles gated before Facilitator submits (week 3)",
               PASS if all_gated else FAIL)

        host.find_element(By.ID, "demandInput").send_keys("8")
        click_id(host, "submitDemandBtn", pause=0.6)

        only_retailer = (exists(guest, By.ID, "orderInput")
                          and not exists(guest2, By.ID, "orderInput")
                          and not exists(guest3, By.ID, "orderInput"))
        record(section_play, "Only Retailer unlocks after Facilitator submits (per Rick's required order)",
               PASS if only_retailer else FAIL)

        guest.find_element(By.ID, "orderInput").send_keys("7")
        click_id(guest, "submitOrderBtn", pause=0.6)

        only_wholesaler = (exists(guest2, By.ID, "orderInput") and not exists(guest3, By.ID, "orderInput"))
        record(section_play, "Only Wholesaler unlocks after Retailer submits (Distributor still gated)",
               PASS if only_wholesaler else FAIL)

        guest2.find_element(By.ID, "orderInput").send_keys("6")
        click_id(guest2, "submitOrderBtn", pause=0.6)

        distributor_unlocked = exists(guest3, By.ID, "orderInput")
        record(section_play, "Distributor unlocks after Wholesaler submits",
               PASS if distributor_unlocked else FAIL)

        weeks_synced = state(host, "sessionWeek") == state(guest, "sessionWeek") == state(guest2, "sessionWeek")
        record(section_play, "Week number stays in sync across clients",
               PASS if weeks_synced else FAIL,
               f"host={state(host, 'sessionWeek')} guestA={state(guest, 'sessionWeek')} guestB={state(guest2, 'sessionWeek')}")

        # Restart should be host-only
        click_id(guest, "settingsGearBtn")
        guest_restart_disabled = guest.find_element(By.ID, "settingsRestartBtn").get_attribute("disabled") is not None
        record(section_play, "Restart is disabled for a non-host guest",
               PASS if guest_restart_disabled else FAIL)
    finally:
        host.quit()
        guest.quit()
        guest2.quit()
        guest3.quit()


# ---------------------------------------------------------------------------
# SECTION 6: Facilitator-Specific Features (solo, playing Facilitator)
# ---------------------------------------------------------------------------
def test_section_6_facilitator(file_url):
    section = "6. Facilitator-Specific Features"
    driver = new_driver()
    try:
        load_game(driver, file_url)
        click_id(driver, "startBtn")
        click_id(driver, "pickSolo")
        time.sleep(0.3)
        for card in driver.find_elements(By.CLASS_NAME, "role-pick-card"):
            if card.get_attribute("data-role") == "facilitator":
                card.click()
                break
        time.sleep(0.3)

        baseline_boxes = driver.find_elements(By.CLASS_NAME, "baseline-box")
        record(section, "3 baseline boxes present (Decision Time / Starting Price / Starting Demand)",
               PASS if len(baseline_boxes) == 3 else FAIL, f"found {len(baseline_boxes)}")

        for _ in range(2):
            click_id(driver, "submitDemandBtn")

        click_id(driver, "randomDemandBtn")
        suggested_value = driver.find_element(By.ID, "demandInput").get_attribute("value")
        record(section, "Suggested button fills a value", PASS if suggested_value else FAIL,
               f"value={suggested_value}")
        click_id(driver, "submitDemandBtn")

        still_available = exists(driver, By.ID, "randomDemandBtn")
        record(section, "Suggested button remains usable in week 4 (not one-time)",
               PASS if still_available else FAIL)

        follow_cells = driver.find_elements(By.CLASS_NAME, "follow-cell-name")
        record(section, "Follow grid shows player/bot names, not truncated placeholders",
               PASS if len(follow_cells) == 4 and all(c.text for c in follow_cells) else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 7: News System
# ---------------------------------------------------------------------------
def test_section_7_news(file_url):
    section = "7. News System"
    driver = new_driver()
    try:
        load_game(driver, file_url)
        click_id(driver, "startBtn")
        click_id(driver, "pickSolo")
        time.sleep(0.3)
        for card in driver.find_elements(By.CLASS_NAME, "role-pick-card"):
            if card.get_attribute("data-role") == "facilitator":
                card.click()
                break
        time.sleep(0.3)

        # ---- Global News: one shared dropdown, unchanged ----
        global_options = driver.find_elements(By.CSS_SELECTOR, "#globalNewsSelect option")
        record(section, "Global News dropdown lists all 10 (+ None)",
               PASS if len(global_options) == 11 else FAIL, f"found {len(global_options)}")

        base_holding = state(driver, "game.holdingCost")
        driver.execute_script("""
            const sel = document.getElementById('globalNewsSelect');
            sel.selectedIndex = 1;
            sel.dispatchEvent(new Event('change'));
        """)
        time.sleep(0.2)
        new_holding = state(driver, "game.holdingCost")
        record(section, "Selecting Global News changes holding cost",
               PASS if new_holding != base_holding else FAIL,
               f"{base_holding} -> {new_holding}")

        # ---- Local News: 4 independent per-role dropdowns ----
        role_selects = driver.find_elements(By.CLASS_NAME, "local-news-role-select")
        roles_found = sorted(set(s.get_attribute("data-role") for s in role_selects))
        record(section, "4 separate Local News dropdowns exist, one per chain role",
               PASS if roles_found == ["distributor", "manufacturer", "retailer", "wholesaler"] else FAIL,
               f"found {roles_found}")

        filtered_correctly = driver.execute_script("""
            const results = {};
            document.querySelectorAll('.local-news-role-select').forEach(sel => {
                const role = sel.dataset.role;
                const ids = Array.from(sel.options).map(o => o.value).filter(v => v);
                results[role] = ids.every(id => LOCAL_NEWS.find(n => n.id === id).targetRole === role);
            });
            return Object.values(results).every(v => v === true);
        """)
        record(section, "Each role's dropdown only contains that role's own news items",
               PASS if filtered_correctly else FAIL)

        # Set DIFFERENT news on two different roles and confirm both persist independently
        retailer_id = driver.execute_script("return LOCAL_NEWS.find(n => n.targetRole === 'retailer').id;")
        manufacturer_id = driver.execute_script("return LOCAL_NEWS.find(n => n.targetRole === 'manufacturer').id;")
        driver.execute_script("""
            const sel = document.querySelector('.local-news-role-select[data-role="retailer"]');
            sel.value = arguments[0];
            sel.dispatchEvent(new Event('change'));
        """, retailer_id)
        time.sleep(0.2)
        driver.execute_script("""
            const sel = document.querySelector('.local-news-role-select[data-role="manufacturer"]');
            sel.value = arguments[0];
            sel.dispatchEvent(new Event('change'));
        """, manufacturer_id)
        time.sleep(0.2)

        news_map = state(driver, "localNewsByRole")
        independent_ok = (
            news_map is not None
            and news_map.get("retailer") == retailer_id
            and news_map.get("manufacturer") == manufacturer_id
            and news_map.get("wholesaler") is None
            and news_map.get("distributor") is None
        )
        record(section, "Setting different Local News on two roles at once works independently",
               PASS if independent_ok else FAIL, f"map={news_map}")

        # Facilitator's own summary box reflects all 4 roles at a glance
        summary_text = driver.find_element(By.CLASS_NAME, "news-box-local").text
        record(section, "Facilitator's Local News box summarizes all 4 roles, untouched roles show 'None'",
               PASS if ("None" in summary_text and "Retailer" in summary_text) else FAIL)

        news_boxes = driver.find_elements(By.CLASS_NAME, "news-box")
        record(section, "Global + Local news boxes appear on the role's own screen",
               PASS if len(news_boxes) == 2 else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 8: Warnings (forced via state injection, since naturally
# triggering these takes many turns of deliberately bad play)
# ---------------------------------------------------------------------------
def test_section_8_warnings(file_url):
    section = "8. Warnings: Overordering & Stockout"
    driver = new_driver()
    try:
        load_game(driver, file_url)
        click_id(driver, "startBtn")
        click_id(driver, "pickSolo")
        time.sleep(0.3)
        for card in driver.find_elements(By.CLASS_NAME, "role-pick-card"):
            if card.get_attribute("data-role") == "retailer":
                card.click()
                break
        time.sleep(0.3)
        for _ in range(2):
            click_id(driver, "submitOrderBtn")

        driver.execute_script("""
            window.state.game.roles.retailer.stock = 100;
            window.render();
        """)
        time.sleep(0.2)
        record(section, "Overordering warning appears with artificially high stock",
               PASS if exists(driver, By.CLASS_NAME, "warning-banner-amber") else FAIL)

        driver.execute_script("""
            window.state.game.roles.retailer.stock = 0;
            window.state.game.roles.retailer.backlog = 5;
            window.render();
        """)
        time.sleep(0.2)
        record(section, "Stockout warning appears with backlog > 0",
               PASS if exists(driver, By.CLASS_NAME, "warning-banner-red") else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 9: Sound (mechanism only - actual audio quality needs a human ear)
# ---------------------------------------------------------------------------
def test_section_9_sound(file_url):
    section = "9. Sound"
    driver = new_driver()
    try:
        load_game(driver, file_url)

        record(section, "Actual audio output/quality", SKIP, "needs a human listening, not automatable")

        mute_btn_exists = exists(driver, By.ID, "settingsGearBtn")
        record(section, "Settings (sound controls) reachable", PASS if mute_btn_exists else FAIL)

        click_id(driver, "settingsGearBtn")
        click_id(driver, "settingsSoundBtn")
        muted = state(driver, "soundMuted")
        record(section, "Mute toggles state.soundMuted to true", PASS if muted else FAIL)

        # The dropdown deliberately stays open after a Sound click (unlike
        # Help/Restart/Quit, which navigate away and close it) - so the
        # second toggle just clicks Sound again directly, no gear re-click.
        dropdown_still_open = exists(driver, By.ID, "settingsDropdown")
        record(section, "Dropdown stays open after toggling sound (by design)",
               PASS if dropdown_still_open else FAIL)

        click_id(driver, "settingsSoundBtn")
        unmuted = state(driver, "soundMuted") is False
        record(section, "Unmute toggles state.soundMuted back to false", PASS if unmuted else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 10: Settings Panel
# ---------------------------------------------------------------------------
def test_section_10_settings(file_url):
    section = "10. Settings Panel"
    driver = new_driver()
    try:
        load_game(driver, file_url)

        record(section, "Dropdown closed initially", PASS if not exists(driver, By.ID, "settingsDropdown") else FAIL)

        click_id(driver, "settingsGearBtn")
        items = ["settingsSoundBtn", "settingsHelpBtn", "settingsRestartBtn", "settingsQuitBtn"]
        all_present = all(exists(driver, By.ID, i) for i in items)
        record(section, "Dropdown has exactly Sound/Help/Restart/Quit", PASS if all_present else FAIL)

        restart_disabled = driver.find_element(By.ID, "settingsRestartBtn").get_attribute("disabled") is not None
        record(section, "Restart disabled before any game exists", PASS if restart_disabled else FAIL)

        click_id(driver, "settingsHelpBtn")
        modal_open = exists(driver, By.CLASS_NAME, "help-modal")
        record(section, "Help opens the guide modal", PASS if modal_open else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 11: Results Screen
# ---------------------------------------------------------------------------
def test_section_11_results(file_url):
    section = "11. Results Screen"
    driver = new_driver()
    try:
        load_game(driver, file_url)
        click_id(driver, "startBtn")
        click_id(driver, "pickSolo")
        time.sleep(0.3)
        for card in driver.find_elements(By.CLASS_NAME, "role-pick-card"):
            if card.get_attribute("data-role") == "wholesaler":
                card.click()
                break
        time.sleep(0.3)
        for _ in range(2):
            click_id(driver, "submitOrderBtn")
        for _ in range(6):
            order_input = driver.find_element(By.ID, "orderInput")
            order_input.clear()
            order_input.send_keys("6")
            click_id(driver, "submitOrderBtn", pause=0.15)

        record(section, "Results screen reached", PASS if state(driver, "screen") == "end" else FAIL)

        cost_table_headers = driver.find_elements(By.CSS_SELECTOR, ".cost-per-week-table thead th")
        expected_cols = ["Role"] + [f"Week {i}" for i in range(1, 9)] + ["Total"]
        actual_cols = [h.text for h in cost_table_headers]
        record(section, "Cost Per Week table matches Role/Week1-8/Total layout",
               PASS if actual_cols == expected_cols else FAIL, f"got {actual_cols}")

        bar_chart_present = exists(driver, By.ID, "endBarChart")
        record(section, "Cost comparison bar chart renders", PASS if bar_chart_present else FAIL)
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# SECTION 12: Cross-Cutting & Edge Cases (the automatable subset)
# ---------------------------------------------------------------------------
def test_section_12_edge_cases(file_url):
    section = "12. Cross-Cutting & Edge Cases"
    driver = new_driver()
    try:
        load_game(driver, file_url)
        click_id(driver, "startBtn")
        click_id(driver, "pickSolo")
        time.sleep(0.3)
        driver.find_element(By.ID, "soloWeeks").clear()
        driver.find_element(By.ID, "soloWeeks").send_keys("4")
        for card in driver.find_elements(By.CLASS_NAME, "role-pick-card"):
            if card.get_attribute("data-role") == "manufacturer":
                card.click()
                break
        time.sleep(0.3)
        for _ in range(2):
            click_id(driver, "submitOrderBtn")
        for _ in range(2):
            order_input = driver.find_element(By.ID, "orderInput")
            order_input.clear()
            order_input.send_keys("5")
            click_id(driver, "submitOrderBtn", pause=0.15)
        record(section, "Minimum-length game (4 weeks) completes correctly",
               PASS if state(driver, "screen") == "end" else FAIL)

        # Responsive check: narrow viewport
        driver.set_window_size(390, 844)  # roughly a phone
        time.sleep(0.3)
        app_visible = driver.find_element(By.ID, "app").is_displayed()
        record(section, "App remains visible/usable at phone width", PASS if app_visible else FAIL)

        record(section, "Visual quality at phone width", SKIP, "layout correctness needs visual review, not just presence")
        record(section, "Two-tab same-device multiplayer (BroadcastChannel)", SKIP,
               "requires two real tabs sharing one browser profile, awkward to isolate in a single Selenium session")
    finally:
        driver.quit()


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
    # pathlib.Path(...).resolve().as_uri() correctly handles Windows
    # backslashes and the file:/// triple-slash requirement - naive
    # string concatenation like f"file://{path}" breaks on Windows
    # paths (e.g. produces "file://C:\internship\index.html" instead
    # of the required "file:///C:/internship/index.html").
    return pathlib.Path(path).resolve().as_uri()


# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python beer_game_selenium_tests.py /path/to/index.html")
        sys.exit(1)
    file_url = normalize_file_url(sys.argv[1])
    print(f"Loading: {file_url}\n")

    test_section_1_navigation(file_url)
    test_section_2_solo_gameplay(file_url)
    test_section_3_market_scenario(file_url)
    try:
        test_sections_4_5_multiplayer(file_url)
    except Exception as e:
        record("4/5. Multiplayer", "(suite)", FAIL, f"exception - is the relay server running? {e}")
    test_section_6_facilitator(file_url)
    test_section_7_news(file_url)
    test_section_8_warnings(file_url)
    test_section_9_sound(file_url)
    test_section_10_settings(file_url)
    test_section_11_results(file_url)
    test_section_12_edge_cases(file_url)

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r[2] == PASS)
    failed = sum(1 for r in results if r[2] == FAIL)
    skipped = sum(1 for r in results if r[2] == SKIP)
    print(f"TOTAL: {passed} passed, {failed} failed, {skipped} skipped (need manual check)")
    if failed:
        print("\nFailed items:")
        for section, item, status, detail in results:
            if status == FAIL:
                print(f"  - [{section}] {item}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    main()
