# -*- coding: utf-8 -*-
"""Geteilte Listenformate einsammeln (läuft als GitHub-Action im öffentlichen Vorlagen-Repo, z. B.
Hansi478/speedrace-dashboard - dort unter .github/sammeln/formate_sammeln.py, gleicher Inhalt wie hier).

Jedes Dashboard mit GitHub-Pages-Weiterleitung und eingeschaltetem „Formate teilen“ schreibt einmal am Tag
speedrace-formate.json in sein Pages-Repo - einen Fork der Vorlage. Dieses Skript
  1. findet die Quellen von selbst: das Vorlagen-Repo und alle seine Forks (öffentliche GitHub-Liste),
  2. holt je Quelle die Datei (höchstens 256 KB) und prüft jedes Format streng: nur bekannte Felder und
     Zellentypen, begrenzte Größen, kein Widerspruch zum eingebauten Wortschatz (aus „Name“ wird nie „Verein“);
     höchstens 50 Formate je Quelle. Aus den Dateien wird nie etwas ausgeführt,
  3. lässt weg, was mindestens zwei Quellen als falsch gelesen melden - oder eine, wenn keine andere Quelle das
     Format hat (so kann ein einzelner Fork nicht die Formate aller anderen entfernen),
  4. behält von Hand hochgeladene Formate (stehen in parser_rezepte.json, stammen aber nicht aus einer Quelle),
  5. schreibt parser_rezepte.json in den Zweig „vorlagen“ (nur bei Änderungen, ein Commit).
Die Dashboards holen die Datei von dort - und trauen ihr nicht blind: jede Liste in einem geteilten Format muss
vor Ort die automatische Prüfung bestehen.

Nur Standardbibliothek. Start (in der Action):  python3 formate_sammeln.py
Umgebung: GITHUB_REPOSITORY (Besitzer/Name), GITHUB_TOKEN; optional FORMATE_TROCKEN=1 (nichts schreiben).
Konnten nicht alle Quellen gelesen werden (Fehler, Abrufgrenze der API), bleiben die bisher gesammelten Formate
erhalten. Die Regeln müssen zu parser.py passen (_GEN_FELDER, _GEN_TYPEN, _GEN_KOPF, _GEN_KOPF_FAMILIEN) - der
Test tests/test_formate_teilen.py prüft das.
"""
import base64
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

DATEI_QUELLE = "speedrace-formate.json"
DATEI_ZIEL = "parser_rezepte.json"
ZWEIG = "vorlagen"
MAX_DATEI = 256 * 1024
MAX_JE_QUELLE = 50
MAX_GESAMT = 500
MAX_FORKS = 1000
MAX_ABRUFE = 900        # GITHUB_TOKEN der Action: 1.000 Anfragen je Stunde und Repository

FELDER = ("platz", "startnr", "name", "nachname", "vorname", "jahrgang", "ak", "geschlecht", "verein", "nat",
          "netto", "brutto", "zeit", "diff", "pace", "kmh", "ak_platz", "mw_platz", "x")
TYPEN = ("rang", "zahl", "zahl2", "jahr", "zeit", "status", "ak", "nat", "g", "diff", "pace", "kmh", "anteil",
         "dezimal", "text")
# eingebauter Wortschatz der Kopfzeilen (wie parser.py _GEN_KOPF)
KOPF = [
    ("ak_platz", r"(ak|kl\.?|klasse|kat\.?)\s?-?\s?(platz|pl\.?|rang|rg\.?)|(platz|pl\.?|rang|rg\.?)\s?(ak|kl\.?|klasse)"),
    ("mw_platz", r"(m/?w|mw|geschl\.?|sex|g)\s?-?\s?(platz|pl\.?|rang|rg\.?)|(platz|pl\.?|rang|rg\.?)\s?(m/?w|mw|geschl\.?)"),
    ("platz", r"platz|pl\.?|plz\.?|rang|rg\.?|pos\.?|position|place|gesamt\s?-?\s?platz|gesamtrang|overall|rank"),
    ("startnr", r"st\.?\s?-?\s?nr\.?|start\s?-?\s?nr\.?|startnummer|bib|nr\.?|#|stnr\.?"),
    ("name", r"name|(teilnehmer|athlet|läufer|sportler|starter)([/*:_]?in(nen)?)?|(nach)?name,?\s?vorname|"
             r"vorname,?\s?(nach)?name|"
             r"name\s?/\s?vorname|participant|runner"),
    ("nachname", r"nachname|familienname|surname|last\s?name"),
    ("vorname", r"vorname|first\s?name"),
    ("jahrgang", r"jg\.?|jahrg\.?|jahrgang|geb\.?|geb\.?\s?jahr|geburtsjahr|yob|year"),
    ("ak", r"ak|klasse|kat\.?|kategorie|altersklasse|age\s?group|ag|wk|wertung"),
    ("geschlecht", r"g|geschl\.?|geschlecht|sex|m/w|gender"),
    ("verein", r"verein|team|club|mannschaft|verein\s?/\s?ort|verein\s?/\s?team|ort\s?/\s?verein|firma|verein/schule"),
    ("nat", r"nat\.?|nation|land|country|nationalität"),
    ("netto", r"netto|nettozeit|chip\s?-?\s?zeit|chiptime|chip"),
    ("brutto", r"brutto|bruttozeit|gun\s?-?\s?time|guntime|gun"),
    ("zeit", r"zeit|endzeit|zielzeit|ergebnis|leistung|time|gesamtzeit|laufzeit|finish"),
    ("diff", r"diff\.?|differenz|rückstand|abstand|gap|behind"),
    ("pace", r"pace|min/km|tempo|schnitt|ø"),
    ("kmh", r"km/h|kmh|geschw\.?"),
]
KOPF_RES = [(f, re.compile(r"^(?:" + rx + r")$", re.I)) for f, rx in KOPF]
FAMILIEN = ({"zeit", "netto", "brutto"}, {"platz", "ak_platz", "mw_platz"}, {"name", "nachname", "vorname"},
            {"ak", "geschlecht"})
UEBERNAHME = ("automatisch", "admin")


def _kopf_norm(t):
    """wie parser.py _gen_kopf_norm"""
    return re.sub(r"\s+", " ", str(t or "").strip().strip(":").lower())


def _text(w, n):
    """Einzeiliger Text ohne Steuerzeichen, gekürzt."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(w or "")).strip()[:n]


def eingebaut(label):
    t = _kopf_norm(label)
    return next((f for f, rx in KOPF_RES if rx.match(t)), None)


def widerspricht(label, feld):
    """True, wenn ein Kopfwort des eingebauten Wortschatzes auf ein fremdes Feld umgedeutet wird."""
    e = eingebaut(label)
    return bool(e) and feld != e and not any(feld in fam and e in fam for fam in FAMILIEN)


def rezept_pruefen(r):
    """-> bereinigtes Format oder (None, Grund)."""
    if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not re.fullmatch(r"[0-9a-f]{12}", r["id"]):
        return None, "Kennung ungültig"
    felder = r.get("felder")
    if not isinstance(felder, list) or not 2 <= len(felder) <= 20 or any(f not in FELDER for f in felder):
        return None, "Felder ungültig"
    kopf = r.get("kopf") or {}
    if not isinstance(kopf, dict) or len(kopf) > 40:
        return None, "Kopfzeile ungültig"
    k_aus = {}
    for label, f in kopf.items():
        label = _text(label, 40).lower()
        if not label or f not in FELDER or f == "x":
            return None, "Kopfzeile ungültig"
        if widerspricht(label, f):
            return None, f"„{label}“ widerspricht dem eingebauten Wortschatz"
        k_aus[label] = f
    sig = r.get("signaturen") or {}
    if not isinstance(sig, dict) or len(sig) > 50:
        return None, "Signaturen ungültig"
    s_aus = {}
    for k, v in sig.items():
        teile = str(k).split("|")
        if not (2 <= len(teile) <= 20 and all(t in TYPEN for t in teile) and isinstance(v, list)
                and len(v) == len(teile) and all(f in FELDER for f in v)):
            return None, "Signaturen ungültig"
        s_aus[str(k)] = list(v)
    erstellt = str(r.get("erstellt") or "")[:10]
    listen = r.get("listen")
    return {"id": r["id"], "felder": list(felder), "kopf": k_aus, "signaturen": s_aus,
            "weg": _text(r.get("weg"), 20), "beschreibung": _text(r.get("beschreibung"), 120),
            "erstellt": erstellt if re.fullmatch(r"\d{4}-\d{2}-\d{2}", erstellt) else "",
            "listen": listen if isinstance(listen, int) and not isinstance(listen, bool) and 0 <= listen < 10 ** 6 else 0,
            "uebernahme": r.get("uebernahme") if r.get("uebernahme") in UEBERNAHME else ""}, ""


def quelle_pruefen(daten):
    """Inhalt einer speedrace-formate.json -> (formate {id: rezept}, falsch {id}, hinweise [Text])."""
    if not isinstance(daten, dict) or daten.get("format") != "speedrace-formate" or daten.get("version") != 1:
        return {}, set(), ["unbekanntes Dateiformat"]
    formate, hinweise = {}, []
    roh = daten.get("rezepte") if isinstance(daten.get("rezepte"), dict) else {}
    for rid, r in list(roh.items())[:MAX_JE_QUELLE]:
        rr, grund = rezept_pruefen(r)
        if rr is None or rr["id"] != rid:
            hinweise.append(f"{str(rid)[:12]}: {grund or 'Kennung passt nicht'}")
            continue
        formate[rid] = rr
    if len(roh) > MAX_JE_QUELLE:
        hinweise.append(f"nur die ersten {MAX_JE_QUELLE} von {len(roh)} Formaten übernommen")
    falsch = {i for i in (daten.get("falsch") or [])[:500] if isinstance(i, str) and re.fullmatch(r"[0-9a-f]{12}", i)} \
        if isinstance(daten.get("falsch"), list) else set()
    return formate, falsch, hinweise


def zusammenfuehren(quellen, bisher, vollstaendig=True):
    """quellen: [(name, daten)], bisher: Inhalt der bisherigen parser_rezepte.json (oder None).
    vollstaendig=False: nicht alle Quellen gelesen - bisher gesammelte Formate bleiben.
    -> (neue Datei ohne Stand, Bericht [Text])"""
    gesammelt, anzahl, melder, bericht = {}, {}, {}, []
    automatisch_alt = set(bisher.get("automatisch") or []) if isinstance(bisher, dict) \
        and isinstance(bisher.get("automatisch"), list) else set()
    for name, daten in quellen:
        formate, f, hinweise = quelle_pruefen(daten)
        for rid in f:
            melder[rid] = melder.get(rid, 0) + 1
        for rid, r in formate.items():
            gesammelt.setdefault(rid, r)
            if rid not in f:
                anzahl[rid] = anzahl.get(rid, 0) + 1
        bericht.append(f"{name}: {len(formate)} Format(e), {len(f)} als falsch gemeldet"
                       + (" - " + "; ".join(hinweise[:5]) if hinweise else ""))
    # weggelassen wird, was zwei Quellen als falsch melden - oder eine, wenn keine andere Quelle es hat
    falsch = {rid for rid, n in melder.items() if n >= 2 or not anzahl.get(rid)}
    # von Hand hochgeladene: in der bisherigen Datei, aber nicht aus dem letzten automatischen Lauf
    manuell = {}
    if isinstance(bisher, dict) and isinstance(bisher.get("rezepte"), dict):
        automatisch = set(bisher.get("automatisch") or []) if isinstance(bisher.get("automatisch"), list) else set()
        for rid, r in bisher["rezepte"].items():
            if rid in gesammelt or (rid in automatisch and vollstaendig):
                continue
            rr, grund = rezept_pruefen(r)
            if rr is not None and rr["id"] == rid:
                manuell[rid] = rr
            else:
                bericht.append(f"von Hand: {str(rid)[:12]} verworfen ({grund or 'Kennung passt nicht'})")
    rezepte = {}
    for rid in sorted(set(gesammelt) | set(manuell)):
        if rid in falsch:
            continue
        r = dict(gesammelt.get(rid) or manuell[rid])
        r["quellen"] = anzahl.get(rid, 0) or (r.get("quellen", 0) if rid in manuell else 0)
        rezepte[rid] = r
        if len(rezepte) >= MAX_GESAMT:
            bericht.append(f"Obergrenze {MAX_GESAMT} Formate erreicht")
            break
    weg = sorted(falsch & (set(gesammelt) | set(manuell)))
    if weg:
        bericht.append(f"{len(weg)} Format(e) weggelassen (als falsch gemeldet)")
    if not vollstaendig:
        bericht.append("nicht alle Quellen gelesen - bisher gesammelte Formate bleiben")
    return {"format": "speedrace-parser-rezepte", "version": 1,
            "hinweis": "Geteilte Listenformate für den allgemeinen Tabellenleser - nur Spaltenbezeichnungen und "
                       "Zellentypen, keine Inhalte. Jedes Dashboard prüft Listen in diesen Formaten selbst.",
            "rezepte": rezepte, "automatisch": sorted(i for i in rezepte if i in gesammelt
                                                      or (not vollstaendig and i in automatisch_alt))}, bericht


# ---------------------------------------------------------------------------------------------------------------
# GitHub (REST-API mit dem Token der Action)
# ---------------------------------------------------------------------------------------------------------------
API = "https://api.github.com"
_abrufe = [0]


def _api(methode, pfad, token, daten=None, roh=False, grenze=MAX_DATEI):
    kopf = {"Accept": "application/vnd.github.raw" if roh else "application/vnd.github+json",
            "User-Agent": "speedrace-formate-sammeln", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        kopf["Authorization"] = f"Bearer {token}"
    body = json.dumps(daten).encode("utf-8") if daten is not None else None
    if body is not None:
        kopf["Content-Type"] = "application/json"
    _abrufe[0] += 1
    req = urllib.request.Request(API + pfad, data=body, headers=kopf, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            inhalt = resp.read(grenze + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if len(inhalt) > grenze:
        raise ValueError("Antwort zu groß")
    return inhalt if roh else (json.loads(inhalt.decode("utf-8")) if inhalt else {})


def quellen_finden(repo, token):
    """Vorlagen-Repo und alle seine Forks (Besitzer/Name)."""
    namen, seite = [repo], 1
    while len(namen) < MAX_FORKS + 1:
        teil = _api("GET", f"/repos/{repo}/forks?per_page=100&page={seite}", token, grenze=4 * 1024 * 1024) or []
        if not teil:
            break
        for f in teil:
            n = (f or {}).get("full_name")
            if isinstance(n, str) and re.fullmatch(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}", n) and n not in namen:
                namen.append(n)
        if len(teil) < 100:
            break
        seite += 1
    return namen[:MAX_FORKS + 1]


def quelle_holen(name, token):
    """speedrace-formate.json einer Quelle (Standardzweig) -> dict, None (keine Datei) oder False (Fehler)."""
    try:
        roh = _api("GET", f"/repos/{name}/contents/{DATEI_QUELLE}", token, roh=True)
        return json.loads(roh.decode("utf-8")) if roh else None
    except (ValueError, UnicodeDecodeError, urllib.error.URLError) as e:
        print(f"  {name}: nicht lesbar ({e.__class__.__name__})")
        return False


def ziel_lesen(repo, token):
    """-> (Inhalt der bisherigen parser_rezepte.json oder None, sha der Datei oder None, Zweig vorhanden?)"""
    info = _api("GET", f"/repos/{repo}/contents/{DATEI_ZIEL}?ref={ZWEIG}", token, grenze=4 * 1024 * 1024)
    if info is None:
        return None, None, _api("GET", f"/repos/{repo}/branches/{ZWEIG}", token) is not None
    daten = json.loads(base64.b64decode(info.get("content") or "").decode("utf-8") or "null")
    return daten, info.get("sha"), True


def ziel_schreiben(repo, token, inhalt_bytes, sha, zweig_da, nachricht):
    if not zweig_da:
        # eigener, leerer Zweig nur mit der Datei (ohne die Dateien der Weiterleitung)
        blob = _api("POST", f"/repos/{repo}/git/blobs", token,
                    {"content": base64.b64encode(inhalt_bytes).decode("ascii"), "encoding": "base64"})
        baum = _api("POST", f"/repos/{repo}/git/trees", token,
                    {"tree": [{"path": DATEI_ZIEL, "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
        commit = _api("POST", f"/repos/{repo}/git/commits", token, {"message": nachricht, "tree": baum["sha"], "parents": []})
        _api("POST", f"/repos/{repo}/git/refs", token, {"ref": f"refs/heads/{ZWEIG}", "sha": commit["sha"]})
        return
    daten = {"message": nachricht, "content": base64.b64encode(inhalt_bytes).decode("ascii"), "branch": ZWEIG}
    if sha:
        daten["sha"] = sha
    _api("PUT", f"/repos/{repo}/contents/{DATEI_ZIEL}", token, daten)


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}", repo):
        print("GITHUB_REPOSITORY fehlt")
        return 2
    namen = quellen_finden(repo, token)
    print(f"{len(namen)} Quelle(n): Vorlage + {len(namen) - 1} Fork(s)")
    quellen, vollstaendig = [], True
    for n in namen:
        if _abrufe[0] >= MAX_ABRUFE:
            print(f"Abrufgrenze erreicht - {len(namen) - namen.index(n)} Quelle(n) beim nächsten Lauf")
            vollstaendig = False
            break
        d = quelle_holen(n, token)
        if d is False:
            vollstaendig = False
        elif d is not None:
            quellen.append((n, d))
    bisher, sha, zweig_da = ziel_lesen(repo, token)
    neu, bericht = zusammenfuehren(quellen, bisher, vollstaendig)
    for zeile in bericht:
        print("  " + zeile)
    vergleich = {k: v for k, v in (bisher or {}).items() if k != "stand"} if isinstance(bisher, dict) else None
    if vergleich == neu:
        print("Keine Änderung.")
        return 0
    neu["stand"] = datetime.date.today().isoformat()
    inhalt = (json.dumps(neu, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")
    print(f"{len(neu['rezepte'])} Format(e) -> {ZWEIG}/{DATEI_ZIEL}")
    if os.environ.get("FORMATE_TROCKEN") == "1":
        return 0
    ziel_schreiben(repo, token, inhalt, sha, zweig_da,
                   f"Geteilte Listenformate: {len(neu['rezepte'])} Format(e) aus {len(quellen)} Quelle(n)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
