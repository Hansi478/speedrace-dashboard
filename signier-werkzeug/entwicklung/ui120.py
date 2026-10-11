import os, sys, tempfile, threading
os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, sys.argv[1]); import signier_werkzeug as W
W._gh = lambda pfad, token, *a, **k: {"tag_name": "v1.2.1", "assets": []} if pfad.endswith("/latest") else (_ for _ in ()).throw(ValueError("404"))
s = W.Server(); url = f"http://127.0.0.1:{s.port}/?t={s.token}"
threading.Thread(target=s.httpd.serve_forever, daemon=True).start()
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = br.new_page(viewport={"width": 1000, "height": 900}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url); pg.wait_for_timeout(1500)
    print("update-knopf:", pg.locator("#update-knopf").inner_text(), pg.locator("#update-knopf").is_visible())
    pg.click('[data-reiter="github"]'); pg.wait_for_timeout(300)
    pg.click("#w-suchen"); pg.wait_for_timeout(800)
    print("status:", pg.locator("#w-status").inner_text())
    pg.screenshot(path=sys.argv[1] + "/ui_120.png", full_page=True)
    print("js:", errs); br.close()
s.httpd.shutdown()
