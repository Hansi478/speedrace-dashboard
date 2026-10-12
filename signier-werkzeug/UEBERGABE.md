# Übergabe: Signier-Werkzeug

Stand 11.10.2026. Dieser Ordner enthält alles zum Signier-Werkzeug aus der Sitzung zum
Speedrace-Dashboard (Repository `Hansi478/live-Ergebnisse`). Er dient nur der Ablage und
gehört später in ein eigenes Repository.

## Was es ist

Ein Windows-Programm (eine `.exe`, gebaut mit PyInstaller), das Software-Versionen mit
Ed25519 signiert und prüft. Format `sr-signatur-1`, dasselbe wie `tools/signieren.py` im
Dashboard:

- `SIGNATUR.json` enthält je Datei die SHA-256-Prüfsumme. Textdateien werden mit
  LF-Zeilenenden gerechnet, Binärdateien unverändert.
- Dazu kommt eine Ed25519-Signatur über `{"format","version","dateien"}` (JSON, sortiert,
  ohne Leerzeichen).

Die Bedienung läuft über eine Seite im Browser auf `127.0.0.1` mit Zufallstoken. Es gibt
mehrere Profile (je Software ein Schlüssel). Das GitHub-Token wird mit Windows-DPAPI
gespeichert.

## Versionen

| Version | Inhalt | Stand |
|---|---|---|
| 1.0.0 | Profile, Signieren/Prüfen (Ordner oder GitHub mit einem Klick) | beim Nutzer im Einsatz, als ZIP geliefert |
| 1.1.0 | setzt beim Hochladen von SIGNATUR.json den Tag `v<Version>` | als ZIP geliefert |
| 1.2.0 | Ablage, Bau, Signieren und Update über GitHub (siehe unten) | **fertig, noch nicht veröffentlicht** |

Warum es 1.1.0 gibt: Das Dashboard nimmt bei „Update aus GitHub“ je Version den Commit,
der die Datei `VERSION` ändert. Dort lag noch die alte `SIGNATUR.json`, deshalb wurde das
Update auf 1.8.4 abgelehnt. Tags haben bei der Versionsauswahl Vorrang. Darum setzt das
Werkzeug jetzt beim Hochladen den Tag auf den signierten Stand.

## Version 1.2.0: Entscheidungen des Nutzers

- Ein **öffentliches** Repository `Hansi478/signier-werkzeug`. Es ist noch nicht angelegt,
  die Integration darf keine Repositories anlegen. Der Nutzer legt es selbst an: Public,
  ohne README.
- Die exe wird mit **GitHub Actions** gebaut (`.github/workflows/bauen.yml`). Auslöser ist
  ein Tag `v*`, gebaut wird unter windows-latest mit Python 3.12. Die Paketversionen
  stehen fest und werden mit Prüfsummen geprüft (`bau-anforderungen.txt`), danach läuft der
  Selbsttest. Das Ergebnis wird nur als **Entwurf** eines Releases abgelegt.
- Signiert wird mit dem **Dashboard-Schlüssel**, öffentlich
  `7OhcbQl3LZIM488s+WIDQMr4YhQmGd4dgyxRgun5XAc=`. Er ist im Werkzeug fest eingebaut
  (`WERKZEUG_SCHLUESSEL`).
- Ablauf: Tag setzen, GitHub baut den Entwurf. Dann im Werkzeug: Reiter „GitHub“ → „Neuen
  Entwurf signieren und veröffentlichen“. Das Werkzeug lädt die exe, signiert sie, hängt
  `SIGNATUR.json` an das Release und veröffentlicht es.
- Update: Beim Start wird `releases/latest` abgefragt, oben erscheint „Update auf x.y.z“.
  Ein Klick lädt exe und Signatur und prüft sie mit dem eingebauten Schlüssel. Danach wird
  die laufende exe in `.alt` umbenannt, die neue eingesetzt und das Werkzeug neu gestartet
  (mit `PYINSTALLER_RESET_ENVIRONMENT=1`). Bei jedem Fehler bleibt die alte exe.

## Nächste Schritte

1. Der Nutzer legt `Hansi478/signier-werkzeug` an (Public, leer) und gibt seinem Token
   dafür „Contents: Read and write“.
2. Den Inhalt dieses Ordners ohne `entwicklung/` und ohne `UEBERGABE.md` als ersten
   Commit nach `main` hochladen. Danach den Tag `v1.2.0` setzen, damit Actions baut.
3. Einmalig: Der Nutzer lädt die exe aus dem Entwurf v1.2.0 von Hand herunter, startet sie
   und signiert damit ihren eigenen Entwurf. Ab dann laufen Updates per Klick.
4. Noch offen: der erste echte Bau auf GitHub und ein echtes Ersetzen der exe unter
   Windows. Bisher ist das nur nachgestellt getestet (`entwicklung/test_werkzeug.py`)
   bzw. unter Wine.
5. Erledigt (laut Nutzer, im Repository `Hansi478/signier-werkzeug`): Alle Actions in
   `bauen.yml` und `pruefen.yml` sind auf vollständige Commit-SHAs festgelegt, die Version
   steht jeweils als Kommentar dahinter. Die Fassung in diesem Ordner ist älter.

## Tests (Entwicklung)

- `entwicklung/test_werkzeug.py` testet Signieren, Prüfen, Profile, Token, GitHub
  (nachgestellt), den Tag setzen bzw. verschieben, Veröffentlichen und das Update mit
  Signaturprüfung. Der Test erwartet eine Kopie von `Hansi478/live-Ergebnisse` unter
  `/home/user/live-ergebnisse` (Variable `REPO`).
- `entwicklung/ui120.py` prüft die Oberfläche im Browser (Playwright, Chromium unter
  `/opt/pw-browsers`).
- Bau unter Wine:
  `wine64 python.exe -m PyInstaller --noconfirm --onefile --noconsole --name Signier-Werkzeug --icon signier.ico --hidden-import cryptography.hazmat.primitives.asymmetric.ed25519 signier_werkzeug.py`.
  Danach `Signier-Werkzeug.exe --selbsttest <Datei>`; die Datei muss mit „OK“ beginnen.

## Regeln des Nutzers (gelten weiter)

- Antworten auf Deutsch.
- Versionsnummern vergibt nur der Nutzer. Vor neuen Funktionen erst nachdenken und fragen:
  eine Tabelle mit Einschätzung, Problemen und Aufwand, dann entscheidet der Nutzer.
- ZIPs nur auf Anfrage.
- Der private Schlüssel verlässt nie den PC des Nutzers. Nie `.pem`-Dateien hochladen.
- Keine privaten Testdateien oder Ergebnislisten hochladen. Vor jedem Hochladen nach
  privaten Namen suchen (Liste in der Dashboard-Sitzung).
- Commits als „Hans-Christoph Rose“ mit den Claude-Trailern.
