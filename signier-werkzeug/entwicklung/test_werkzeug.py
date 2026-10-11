import io, json, os, shutil, subprocess, sys, tempfile, threading, urllib.request, zipfile, importlib.util
HIER = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/user/live-ergebnisse"
tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = os.path.join(tmp, "appdata")
sys.path.insert(0, HIER); import signier_werkzeug as W
fehler = []
def check(c, t):
    if not c: fehler.append(t)
srv = W.Server(); threading.Thread(target=srv.httpd.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{srv.port}"
def api(name, d=None, token=srv.token, host=None):
    h = {"X-Token": token, "Content-Type": "application/json"}
    if host: h["Host"] = host
    req = urllib.request.Request(B + "/api/" + name, data=json.dumps(d or {}).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
# Schutz
check(api("zustand", token="falsch")[0] == 403, "falsches Token angenommen")
check(api("zustand", host="boese.example")[0] == 403, "fremder Host angenommen")
try: urllib.request.urlopen(B + "/?t=falsch"); check(False, "Seite ohne Token")
except urllib.error.HTTPError as e: check(e.code == 403, "Seite ohne Token")
with urllib.request.urlopen(B + "/?t=" + srv.token) as r: check(b"Signier-Werkzeug" in r.read(), "Seite fehlt")
# Profil + Schlüssel
c, z = api("profil_speichern", {"name": "Speedrace-Dashboard", "regel": "speedrace", "repo": "Hansi478/live-Ergebnisse", "zweig": "main"})
check(c == 200 and len(z["profile"]) == 1, f"Profil: {c} {z}")
pid = z["profile"][0]["id"]
check(api("schluessel_neu", {"id": pid, "kennwort": "kurz"})[0] == 400, "kurzes Kennwort")
c, z = api("schluessel_neu", {"id": pid, "kennwort": "Werkzeug-Test-123"})
oeff = z["profile"][0]["oeffentlich"]; check(c == 200 and len(oeff) == 44, f"Schlüssel: {z}")
check(b"ENCRYPTED" in open(os.path.join(os.environ["APPDATA"], "Signier-Werkzeug", "schluessel", pid + ".pem"), "rb").read(), "Schlüssel unverschlüsselt")
# Ordner signieren (Kopie des Repos, nur Git-Dateien)
kopie = os.path.join(tmp, "kopie"); os.makedirs(kopie)
dateien = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True).stdout.split()
for f in dateien:
    os.makedirs(os.path.dirname(os.path.join(kopie, f)) or kopie, exist_ok=True); shutil.copy2(os.path.join(REPO, f), os.path.join(kopie, f))
check(api("signieren_ordner", {"id": pid, "kennwort": "falsch-falsch-1", "ordner": kopie})[0] == 400, "falsches Kennwort")
c, d = api("signieren_ordner", {"id": pid, "kennwort": "Werkzeug-Test-123", "ordner": kopie}); check(c == 200, f"signieren: {d}")
c, d = api("pruefen_ordner", {"id": pid, "ordner": kopie}); check(d["pruefung"]["ok"], f"prüfen: {d}")
# gegenprüfen mit Dashboard und Updatehelfer
sys.path.insert(0, REPO); import app
os.environ["SR_UPDATE_SCHLUESSEL"] = oeff
items, _ = app._update_plan(kopie)
check(app._update_signatur_pruefen(kopie, items) == open(os.path.join(REPO, "VERSION")).read().strip(), "Dashboard lehnt ab")
spec = importlib.util.spec_from_file_location("h", os.path.join(REPO, "tools", "update_einspielen.py")); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
teile = [n for n in E.ERLAUBTE_DATEIEN + E.ERLAUBTE_ORDNER if os.path.exists(os.path.join(kopie, n))]
try: E.signatur_pruefen(kopie, teile, oeff)
except ValueError as e: check(False, f"Helfer lehnt ab: {e}")
open(os.path.join(kopie, "parser.py"), "a").write("# x\n")
c, d = api("pruefen_ordner", {"id": pid, "ordner": kopie}); check(not d["pruefung"]["ok"] and "parser.py" in d["pruefung"]["abweichend"], f"Veränderung nicht erkannt: {d}")
# Import eines vorhandenen Schlüssels (tools/signieren.py)
pem = os.path.join(tmp, "alt.pem")
r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "signieren.py"), "schluessel", pem], env=dict(os.environ, SR_SIGNATUR_KENNWORT="Alter-Schluessel-1"), capture_output=True, text=True)
alt_oeff = r.stdout.strip().splitlines()[-1]
c, z = api("profil_speichern", {"name": "Alt", "regel": "alle"}); pid2 = z["profile"][1]["id"]
check(api("schluessel_import", {"id": pid2, "pfad": pem, "kennwort": "falsch"})[0] == 400, "Import mit falschem Kennwort")
c, z = api("schluessel_import", {"id": pid2, "pfad": pem, "kennwort": "Alter-Schluessel-1"})
check(c == 200 and z["profile"][1]["oeffentlich"] == alt_oeff, f"Import: {z}")
# allgemeines Profil: alle Dateien mit Ausnahmen
allg = os.path.join(tmp, "allg"); os.makedirs(os.path.join(allg, "logs")); open(os.path.join(allg, "a.py"), "w").write("x\r\n"); open(os.path.join(allg, "logs", "x.log"), "w").write("1")
api("profil_speichern", {"id": pid2, "name": "Alt", "regel": "alle", "ausschluss": "logs/*"})
c, d = api("signieren_ordner", {"id": pid2, "kennwort": "Alter-Schluessel-1", "ordner": allg}); check(c == 200 and "1 Dateien" in d["meldung"], f"allgemein: {d}")
open(os.path.join(allg, "logs", "x.log"), "w").write("2"); open(os.path.join(allg, "a.py"), "w").write("x\n")
check(api("pruefen_ordner", {"id": pid2, "ordner": allg})[1]["pruefung"]["ok"], "Ausnahme/CRLF")
# GitHub (nachgestellt)
api("token_speichern", {"token": "github_pat_" + "A" * 40})
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w") as z:
    for f in dateien: z.write(os.path.join(REPO, f), "live-Ergebnisse-abc1234/" + f)
    z.writestr("live-Ergebnisse-abc1234/../../boese.txt", "x")
hochgeladen, tags, aufrufe = {}, {}, []
STAND, NEU = "abc1234def" + "0" * 30, "fff0001" + "1" * 33
def gh(pfad, token, methode="GET", daten=None, roh=False, timeout=60):
    check(token == "github_pat_" + "A" * 40, "Token falsch übergeben")
    aufrufe.append((methode, pfad))
    if "/branches/" in pfad: return {"commit": {"sha": STAND}}
    if "/zipball/" in pfad: return zbuf.getvalue()
    if "/contents/SIGNATUR.json" in pfad and methode == "GET":
        if hochgeladen: return {"sha": "blob1", "content": hochgeladen["content"]}
        raise ValueError("404")
    if methode == "PUT": hochgeladen.update(daten); return {"commit": {"sha": NEU}}
    if "/git/ref/tags/" in pfad:
        n = pfad.rsplit("/", 1)[1]
        if n in tags: return {"object": {"sha": tags[n]}}
        raise ValueError("404")
    if methode == "POST" and pfad.endswith("/git/refs"): tags[daten["ref"].rsplit("/", 1)[1]] = daten["sha"]; return {}
    if methode == "PATCH" and "/git/refs/tags/" in pfad:
        check(daten.get("force") is True, "Tag ohne force verschoben"); tags[pfad.rsplit("/", 1)[1]] = daten["sha"]; return {}
    raise ValueError("404")
W._gh = gh
VER = open(os.path.join(REPO, "VERSION")).read().strip()
tags["v" + VER] = "0" * 40   # alter Tag derselben Version -> wird verschoben
c, d = api("signieren_github", {"id": pid, "kennwort": "Werkzeug-Test-123"}); check(c == 200 and hochgeladen.get("branch") == "main", f"GitHub: {d}")
check(tags.get("v" + VER) == NEU and f"Tag v{VER} gesetzt" in d["meldung"], f"Tag nicht auf den Signatur-Commit: {tags} {d}")
# noch einmal signieren (gleicher Inhalt): kein neuer Commit, Tag auf den aktuellen Stand
puts = sum(1 for m, _p in aufrufe if m == "PUT"); del tags["v" + VER]
c, d = api("signieren_github", {"id": pid, "kennwort": "Werkzeug-Test-123"})
check(c == 200 and sum(1 for m, _p in aufrufe if m == "PUT") == puts and tags.get("v" + VER) == STAND
      and "schon aktuell" in d["meldung"], f"unverändert: {d} {tags}")
import base64
sig = json.loads(base64.b64decode(hochgeladen["content"]))
ziel = os.path.join(tmp, "gh"); os.makedirs(ziel)
for f in dateien: os.makedirs(os.path.dirname(os.path.join(ziel, f)) or ziel, exist_ok=True); shutil.copy2(os.path.join(REPO, f), os.path.join(ziel, f))
open(os.path.join(ziel, "SIGNATUR.json"), "w").write(base64.b64decode(hochgeladen["content"]).decode())
items, _ = app._update_plan(ziel)
check(app._update_signatur_pruefen(ziel, items), "hochgeladene Signatur passt nicht zum Repo-Stand")
check(not os.path.exists(os.path.join(tmp, "boese.txt")) and not os.path.exists(os.path.join(os.path.dirname(tmp), "boese.txt")), "Zip-Ausbruch")
# Profil löschen benennt Schlüssel nur um
api("profil_loeschen", {"id": pid2})
check(any(".geloescht-" in n for n in os.listdir(os.path.join(os.environ["APPDATA"], "Signier-Werkzeug", "schluessel"))), "Schlüssel beim Löschen entfernt")
srv.httpd.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
print("FEHLER:\n  " + "\n  ".join(fehler) if fehler else "OK - Signier-Werkzeug")

# ---- 1.2.0: eigenes Release signieren/veröffentlichen und Update einspielen
fehler2 = []
def check2(c, t):
    if not c: fehler2.append(t)
import base64 as _b64, hashlib as _hl
from cryptography.hazmat.primitives import serialization as _ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as _K
tmp2 = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp2
herausgeber = _K.generate()
W.WERKZEUG_SCHLUESSEL = W.oeffentlich_text(herausgeber)
d = {"profile": [{"id": "herausgeber01", "name": "Speedrace", "oeffentlich": W.WERKZEUG_SCHLUESSEL, "regel": "speedrace"}],
     "github_token": W.geheim_speichern("github_pat_" + "B" * 40)}
W.profile_speichern(d)
open(W.schluessel_pfad(d["profile"][0]), "wb").write(herausgeber.private_bytes(_ser.Encoding.PEM, _ser.PrivateFormat.PKCS8,
                                                                             _ser.BestAvailableEncryption(b"Herausgeber-123")))
exe_neu = b"MZ" + os.urandom(6 * 1024 * 1024)
gh_rel = {"id": 77, "draft": True, "tag_name": "v9.9.9", "assets": [{"id": 1, "name": "Signier-Werkzeug.exe", "url": "https://api.github.com/a/1",
          "browser_download_url": "https://github.com/dl/exe"}]}
hoch = {}
def gh2(pfad, token, methode="GET", daten=None, roh=False, timeout=60):
    if pfad.endswith("/releases?per_page=30"): return [gh_rel, {"draft": True, "tag_name": "v1.0.0", "assets": []}]
    if pfad.endswith("/releases/latest"):
        if gh_rel["draft"]: raise ValueError("Repository oder Zweig nicht gefunden (bei privatem Repository: Token nötig).")
        return gh_rel
    if methode == "PATCH" and pfad.endswith("/releases/77"): gh_rel.update(draft=daten["draft"] is True); return {}
    if methode == "DELETE": gh_rel["assets"] = [a for a in gh_rel["assets"] if a["name"] != "SIGNATUR.json"]; return b""
    raise ValueError("404 " + pfad)
def laden2(url, token=None, limit=W._EXE_MAX, accept=""):
    if url in ("https://api.github.com/a/1", "https://github.com/dl/exe"): return exe_neu
    if url == "https://github.com/dl/sig": return hoch["sig"]
    raise ValueError(url)
def hochladen2(rid, name, daten, token):
    check2(rid == 77 and name == "SIGNATUR.json" and token == "github_pat_" + "B" * 40, "Upload falsch")
    hoch["sig"] = daten; gh_rel["assets"].append({"id": 2, "name": "SIGNATUR.json", "browser_download_url": "https://github.com/dl/sig"})
W._gh, W._herunterladen, W._gh_hochladen = gh2, laden2, hochladen2
check2(W.aktion("update_suchen", {})["neuer"] is False, "Entwurf schon als Update sichtbar")
try:
    W.aktion("werkzeug_veroeffentlichen", {"kennwort": "falsch"}); check2(False, "falsches Kennwort angenommen")
except ValueError: pass
r = W.aktion("werkzeug_veroeffentlichen", {"kennwort": "Herausgeber-123"})
check2(r.get("ok") and gh_rel["draft"] is False and "9.9.9" in r["meldung"], f"Veröffentlichen: {r} {gh_rel}")
W.werkzeug_veroeffentlichen  # noqa
check2(W.aktion("update_suchen", {})["neuer"] is True, "Update nicht angeboten")
# Update: laufende exe wird ersetzt, alte bleibt als .alt
lauf = os.path.join(tmp2, "Signier-Werkzeug.exe"); open(lauf, "wb").write(b"MZalt")
W._laufende_exe = lambda: lauf
r = W.aktion("update_einspielen", {})
check2(r.get("neustart") and open(lauf, "rb").read() == exe_neu and open(lauf + ".alt", "rb").read() == b"MZalt", f"Update: {r}")
# manipuliertes Programm -> abgelehnt, nichts ersetzt
open(lauf, "wb").write(b"MZalt"); os.remove(lauf + ".alt")
exe_neu = b"MZ" + os.urandom(6 * 1024 * 1024)
try:
    W.aktion("update_einspielen", {}); check2(False, "veränderte exe eingespielt")
except ValueError as e:
    check2("Signatur" in str(e), f"Meldung: {e}")
check2(open(lauf, "rb").read() == b"MZalt" and not os.path.exists(lauf + ".neu"), "bei Fehler verändert")
# fremder Schlüssel
fremd = _K.generate()
try:
    W.werkzeug_signatur_pruefen(W.werkzeug_signatur_inhalt(fremd, "9.9.9", exe_neu).encode(), exe_neu, "9.9.9"); check2(False, "fremder Schlüssel angenommen")
except ValueError: pass
# falsche Version in der Signatur
try:
    W.werkzeug_signatur_pruefen(W.werkzeug_signatur_inhalt(herausgeber, "9.9.8", exe_neu).encode(), exe_neu, "9.9.9"); check2(False, "andere Version angenommen")
except ValueError: pass
# Weiterleitung ohne Token
import urllib.request as _ur
rq = _ur.Request("https://api.github.com/x", headers={"Authorization": "Bearer geheim"})
neu = W._OhneAuthWeiter().redirect_request(rq, None, 302, "Found", {}, "https://objects.githubusercontent.com/y")
check2(neu is not None and not neu.has_header("Authorization"), "Token wird an den Download-Server weitergegeben")
shutil.rmtree(tmp2, ignore_errors=True)
print("FEHLER 1.2.0:\n  " + "\n  ".join(fehler2) if fehler2 else "OK - Werkzeug 1.2.0: Release signieren, Update mit Signaturprüfung")
