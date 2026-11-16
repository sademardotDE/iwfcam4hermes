# Aufgabenstand — iwfcam4hermes

Stand: **16.11.2026**, Version **0.17.0** (25 Tools).
Doku: [README.md](README.md) · [docs/PROTOCOL.md](docs/PROTOCOL.md) ·
[docs/BLE_PROVISIONING.md](docs/BLE_PROVISIONING.md) ·
[docs/screenshots/](docs/screenshots/README.md)

## Erledigt

### Protokoll & Empfänger
- [x] Z-IOT-Signalisierung (TCP 8882), Login `0x8000`, Zeit/Ready/Keepalive, Media-Ziel `0x9003`
- [x] STUN-Responder (UDP 13478), RTP/JPEG (PT26) + PCMU (PT0)
- [x] Selbstgehosteter Empfänger mit mehreren Kameras: **eigener UDP-Media-Port pro Login**
      (MediaHub), Zustände `streaming`/`paused`/`offline` inkl. Frame-Alter
- [x] AP-Modus-RTSP (`192.168.1.1:7070`, UDP) als lokaler Weg ohne Cloud

### Relay & Vorschau
- [x] Lokaler Relay-Dienst (systemd-User-Unit, `hermes cameras relay-install`)
- [x] HTTP-Vorschau `/status`, `/cameras`, `/snapshot.jpg`, `/stream.mjpg`
      (pro Kamera per `?uid=`, Qualität `original/high/medium/low`, FPS-Limit)
- [x] Snapshot-Ringpuffer: periodische Ablage je Kamera, Retention, `/snapshots`,
      Sofort-Speichern (Dashboard/Desktop/Tool)
- [x] **Watchdog** (opt-in): offline Kameras mit sichtbarem ZIOTA-AP automatisch
      neu provisionieren (Cooldown, Status/Sofortlauf via Tool/UI/HTTP)
- [x] **Poll-Fix**: `?poll=1` liefert 200 + `image: null` statt 502 (kein Log-Spam)
- [x] **Bewegungsmelder** (opt-in): Frame-Differenz, Ereignisse mit Score, Snapshot-Ablage, UI-Badge
- [x] **Telegram sendet Foto** (`sendPhoto` + Caption, Fallback Text)
- [x] **Bewegungsmeldungen**: mehrere typisierte Webhooks (`relay_motion_webhooks`: slack/discord/ntfy/telegram/generic), Test-Benachrichtigung, `camera_motion wait` für Agent/cron

### Einrichtung & Provisionierung
- [x] Kamera-CRUD + Test/Snapshot (JSON-Store, atomar, `.bak`, `0600`)
- [x] Autoconf: WLAN-AP-Scan, BLE-Advertising (mit `bleak`-Fallback), aktueller AP + RTSP
- [x] AP-Provisionierung (TCP 8266, `0x8001`-ACK), WLAN-Daten werden lokal gemerkt
- [x] **Statik-IP-Fallback**, wenn der Kamera-AP keinen DHCP liefert (live verifiziert)
- [x] `camera_reconnect`: offline Kamera mit gemerkten Daten neu provisionieren
- [x] Hermes-Desktop-Seite (`/iwfcam`) + Dashboard-Tab (beide mit Live-Vorschau,
      Zuständen, Reconnect, Snapshot-Ablage, Watchdog)

### Qualität & Oberfläche
- [x] Qualitäts-/FPS-Auswahl für Vorschau und Snapshots (Pillow-Re-Encoding)
- [x] Mehrkamera-Kacheln, Offline-Platzhalter, Löschbestätigung im Desktop
- [x] Einheitliche UID-Behandlung (`ZIOTA_`-Präfix optional)

### Tests & Doku
- [x] 155 Kern-Tests + 26 Dashboard-API-Tests (FastAPI TestClient, eigenes Test-Venv)
- [x] Validator/Doctor: 24 Tools, Manifest + Desktop-Surface OK
- [x] README, PROTOCOL, BLE_PROVISIONING, Screenshots (`docs/screenshots/`)
- [x] Ausgebaute Doku: ARCHITECTURE, API, CONFIGURATION, MOTION, TROUBLESHOOTING,
      SECURITY + erweitertes README (Schnellstart, Architektur, API-Kurzreferenz,
      Telegram-Anleitung, FAQ, Entwicklung, Fehlersuche)

### Verifiziert auf echter Hardware
- [x] Kamera 1 (`ZIOTA_196758286858`, `TXW817_A`): streaming 640×480 über Relay
- [x] Kamera 2 (`ZIOTA_635572396930`, `TXW817_D`): mehrfach neu provisioniert,
      streaming 240×320, **parallel zu Kamera 1** (getrennte UDP-Ports)
- [x] Kamera 2 per BLE erkannt (`2C:4B:63:A5:E4:46`), AP-Provisionierung inkl. Statik-IP
- [x] Snapshots/Qualitätsstufen beider Kameras, Watchdog-Status/Sofortlauf

## Offen / bewusst nicht umgesetzt

- [ ] **BLE-Provisioning auf `TXW817_D`**: Verbindung klappt, aber die Kamera
      exponiert unter BlueZ keine GATT-Services → AP-Weg (8266) bleibt Standard.
- [ ] Kamera-interne Stream-Qualität/Auflösung ist per Protokoll nicht einstellbar;
      Qualitätsstufen betreffen nur Vorschau/Snapshots (serverseitig).
- [ ] Kamera 2 schläft sporadisch ein (Firmware); sichtbar als `paused`/`offline`,
      Watchdog greift nur bei sichtbarem AP.
- [ ] Optional: Snapshot-Tagesordner/Zeitfenster, Ereignis-Log im UI,
      Push-Benachrichtigung bei Offline-Erkennung.
- [ ] Kamera-GUI (`camera_gui.py`) braucht cv2/Tk — auf diesem Host nicht installiert.

## Umgebung (Referenz)

- Relay: `~/.config/systemd/user/iwfcam4hermes-relay.service`, HTTP `127.0.0.1:8099`,
  Signaling 8882, STUN 13478, Snapshots `~/.hermes/iwfcam4hermes/snapshots/`
- Kamera-Config: `~/.hermes/iwfcam4hermes/config.json` (inkl. `"provision"`-Block)
- Hermes: Plugin in `~/.hermes` + Profilen `reverser`/`scout`/`tester`
- Watchdog: `relay_watchdog=true`, Intervall 300 s, Cooldown 1800 s
