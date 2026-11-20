"""Prove the built guide works with no connection.

Starts `fieldguide serve`, opens the site in headless Chromium at phone size,
waits until the service worker has cached everything, cuts the network,
reloads, runs a search with a typo, opens the top result and checks that the
section, its highlighted terms and its page reference are shown.

Usage (needs Playwright with Chromium):
    python scripts/offline_check.py [--site site] [--port 8101] [--query "turn off gass"]
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def default_server_python() -> str:
    for p in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable


def wait_for_server(url: str, timeout: float = 15) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except OSError:
            time.sleep(0.3)
    raise SystemExit(f"server at {url} did not start")


def launch(pw):
    try:
        return pw.chromium.launch()
    except Exception:
        # The Chromium build matching this Playwright is not downloaded: use one that is.
        found = sorted(glob.glob(os.path.expanduser(
            "~/AppData/Local/ms-playwright/chromium*/*/*chrome*.exe")) + glob.glob(os.path.expanduser(
            "~/.cache/ms-playwright/chromium*/*/chrome*")))
        if not found:
            raise
        return pw.chromium.launch(executable_path=found[-1])


def check(label: str, ok: bool) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=str(ROOT / "site"))
    ap.add_argument("--port", type=int, default=8101)
    ap.add_argument("--query", default="shut of gass")
    ap.add_argument("--server-python", default=default_server_python())
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    url = f"http://localhost:{args.port}/"

    server = subprocess.Popen(
        [args.server_python, "-m", "fieldguide.cli", "serve", args.site, "--port", str(args.port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(url)
        with sync_playwright() as pw:
            browser = launch(pw)
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            page = ctx.new_page()

            page.goto(url)
            page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null",
                                   timeout=60_000)
            page.wait_for_function("document.getElementById('status-text').textContent === 'Saved for offline'",
                                   timeout=60_000)
            cached = page.evaluate(
                "caches.keys().then(k => caches.open(k[0])).then(c => c.keys()).then(r => r.length)")
            check(f"service worker active, {cached} files cached", cached > 5)

            ctx.set_offline(True)
            page.reload()
            page.wait_for_selector("body[data-ready='1']", timeout=15_000)
            check("page reloads with the network off", True)
            status = page.text_content("#status-text")
            check(f"status shows offline ({status!r})", "Offline" in (status or ""))
            network_dead = page.evaluate(
                "fetch('/not-cached-' + Date.now()).then(() => false).catch(() => true)")
            check("a request outside the cache fails (really offline)", network_dead)

            page.fill("#q", args.query)
            page.wait_for_selector(".result a", timeout=5_000)
            n = page.locator(".result").count()
            first = page.text_content(".result .r-title")
            check(f"search {args.query!r} offline: {n} results, top: {first!r}", n > 0)

            page.click(".result a")
            page.wait_for_selector("article h1", timeout=5_000)
            title = page.text_content("article h1")
            marks = page.locator("article .body mark, article h1 mark").count()
            src = page.text_content("article .src .pg")
            check(f"opened section {title!r} with {marks} highlighted terms", marks > 0)
            check(f"shows the source page ({src!r})", "of the original" in (src or ""))
            browser.close()
        print("OFFLINE CHECK PASSED")
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
