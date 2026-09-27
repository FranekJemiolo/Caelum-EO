"""Automated High-Resolution Screenshot Capture for Project Caelum-EO.

Uses Playwright in a 100% private/incognito browser context to record authentic visual
proof of the operational Caelum-EO system:
1. 01_login_portal.png - Defense-grade OAuth2 RBAC login portal.
2. 02_tactical_hud_map.png - WebGL 3D extruded vector surveillance map with temporal scrubber.
3. 03_target_dossier.png - Target intelligence dossier with geodesic measurements.
4. 04_multi_temporal_inspector.png - Multi-temporal T0 vs T1 swipe comparison inspector.
5. 05_hitl_reclassification.png - Human-in-the-loop review and audit modal.
"""

import os
import time

from playwright.sync_api import sync_playwright

output_dir = os.path.abspath("docs/screenshots")
os.makedirs(output_dir, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # Always private/incognito context in Playwright
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        device_scale_factor=2,  # Crisp high-DPI quality
    )
    page = context.new_page()

    # 1. Login Screen
    print("1/5 Navigating to http://127.0.0.1:3000...")
    page.goto("http://127.0.0.1:3000", wait_until="networkidle")
    time.sleep(1)
    login_path = os.path.join(output_dir, "01_login_portal.png")
    page.screenshot(path=login_path)
    print(f"[✓] Captured Login Portal: {login_path}")

    # 2. Authenticate as Administrator
    print("2/5 Selecting Admin credentials and authenticating...")
    page.click("button:has-text('Admin')")
    time.sleep(0.3)
    page.click("button[type='submit']")
    page.wait_for_selector("text=CAELUM-EO", timeout=15000)
    time.sleep(3.5)  # Allow WebGL Deck.gl canvas to initialize and render features

    hud_path = os.path.join(output_dir, "02_tactical_hud_map.png")
    page.screenshot(path=hud_path)
    print(f"[✓] Captured Tactical HUD Map: {hud_path}")

    # 3. Select a target from the Triage Hotlist to display Target Dossier
    print("3/5 Selecting target from hotlist to open Target Dossier...")
    # Click the detection card body
    first_card = page.locator("div.p-3.rounded-lg.cursor-pointer").first
    first_card.click()
    time.sleep(1.5)

    dossier_path = os.path.join(output_dir, "03_target_dossier.png")
    page.screenshot(path=dossier_path)
    print(f"[✓] Captured Target Intelligence Dossier: {dossier_path}")

    # 4. Open Multi-Temporal Inspector Modal via Inspect button
    print("4/5 Opening Multi-Temporal Inspector...")
    inspect_btn = page.locator("button:has-text('Inspect')").first
    inspect_btn.click()
    page.wait_for_selector("text=MULTI-TEMPORAL CHIP INSPECTOR", timeout=10000)
    time.sleep(2)

    inspector_path = os.path.join(output_dir, "04_multi_temporal_inspector.png")
    page.screenshot(path=inspector_path)
    print(f"[✓] Captured Multi-Temporal Inspector: {inspector_path}")

    # 5. Transition to HITL Review Modal via "Triage & Label"
    print("5/5 Opening HITL Review Modal...")
    page.click("button:has-text('Triage & Label')")
    page.wait_for_selector("text=HITL TRIAGE", timeout=10000)
    time.sleep(1.5)

    review_path = os.path.join(output_dir, "05_hitl_reclassification.png")
    page.screenshot(path=review_path)
    print(f"[✓] Captured HITL Review Modal: {review_path}")

    context.close()
    browser.close()
    print("\nAll 5 high-resolution proof screenshots successfully captured!")
