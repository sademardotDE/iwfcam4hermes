# Fehlersuche — iwfcam4hermes

Version 0.17.0 · Stand 16.11.2026

## Erste Diagnose (Copy & Paste)

```bash
# Dienste
systemctl --user is-active iwfcam4hermes-relay.service hermes-gateway.service hermes-dashboard.service

# Relay-Status (Kameras, Zustände, Motion, Watchdog)
curl -s http://127.0.0.1:8099/status | jq '{totals, motion, watchdog}'
curl -s http://127.0.0.1:8099/cameras | jq '.cameras[] | {uid,state,frames,last_frame_age_s}'

# Plugin/Tools
hermes plugins doctor iwfcam4hermes
hermes cameras list
hermes cameras relay-status

# Logs
journalctl --user -u iwfcam4hermes-relay.service -n 100 --no-pager
journalctl --user -u hermes-gateway.service -n 100 --no-pager | grep -i iwfcam
```

## Symptome

| Symptom | Ursache / Prüfung | Lösung |
| --- | --- | --- |
| Kein Kamerabild, `state=offline` | Kamera nicht im WLAN / Signaling weg. `ping <kamera-ip>`, `ss -tn \| grep 8882` | Kamera aufwecken/einschalten; `hermes cameras reconnect <id>` (nur wenn AP sichtbar) |
| `state=paused`, Frames stehen | Kamera schläft/pausiert, Signaling lebt (Keepalive) | Normal; Kamera wecken, Motion/Stream prüfen |
| Relay liefert 502/leeres Bild | Kamera nicht verbunden/keine Frames; bei `?poll=1` ist `image:null` normal | Status prüfen, warten oder Kamera wecken |
| „Kamera-AP … nicht sichtbar“ beim Reconnect | Kamera nicht im AP-Modus (schläft/aus) | Kamera stromlos/Reset; danach Provisionierung |
| Provisionierung ohne DHCP | Kamera-AP liefert keine IP | Plugin setzt automatisch `192.168.1.2/24` (seit 0.11.6) — Log prüfen: `journalctl … \| grep statische` |
| TCP 8266 antwortet nicht | AP-Modus-Server der Kamera tot | Kamera stromlos/Reset; ggf. BLE probieren |
| `bleak nicht installiert` | BLE-Scan ohne bleak | Plugin nutzt Fallback (`/usr/bin/python3`); sonst `pip install bleak`, `IWFCAM_BLE_PYTHON` setzen |
| Watchdog macht nichts | kein sichtbarer AP oder kein Cooldown/Config | `curl /watchdog`, `relay_watchdog=true`, AP sichtbar? Cooldown 1800 s beachten |
| Keine Bewegungsereignisse | Motion aus, keine streamende Kamera, Szene statisch | `relay_motion=true`, `GET /motion` (`score`), Sensitivität erhöhen |
| Zu viele Bewegungsmeldungen | Empfindlichkeit zu hoch / IR-Wechsel | Sensitivität senken (z. B. 35–45), Cooldown erhöhen |
| Telegram kommt nicht an | Webhook leer/falsch, Token/Chat-ID, Netz | `POST /motion/test`; Journal `motion webhook …`; `getMe`/`sendMessage` mit Token testen |
| Telegram-Foto fehlt, Text kommt | Bild-Upload fehlgeschlagen (Fallback) | Journal `telegram … failed`; Mode `document`/`photo` prüfen |
| Bewegungsbild erscheint nicht auf USB-Display | USB-Plugin nicht geladen, Dienst aus, falsches Hermes-Home | `camera_display status`, `/display`, `systemctl --user status usb-smart-dashboard.service`, `journalctl … \| grep image` |
| „USB-Smart-Dashboard ist nicht geladen" beim Test | Plugin inaktiv/anderes Profil | `hermes plugins list \| grep usb`, im aktiven Home aktivieren |
| Display zeigt dauerhaft Stats statt Bild | Inbox abgelaufen oder Renderer liest anderes Home | Dauer erhöhen, `show-image.json` prüfen, Dienst neu starten |
| Snapshot-Ablage wächst nicht | `snapshot_dir` leer/Relay aus, Kamera offline | `GET /snapshots`; `relay_snapshot_interval`; Dienststatus |
| Snapshot-Ablage zu voll | Retention zu hoch | `relay_snapshot_retain` senken, `POST /snapshots/save` |
| `Gateway draining`/`ticket control socket missing` | Gateway-Neustart, alte Desktop-Instanz | Desktop neu starten; kurz warten |
| Dashboard-Login-Schleife | Session abgelaufen (Dashboard neu gestartet) | neu einloggen |
| Desktop-Seite leer/Fehler | Plugin-Hälfte veraltet | `hermes plugins install … --force`, dann Desktop neu starten |
| `unit not found`/Dienst startet nicht | `relay_install` nie gelaufen | `hermes cameras relay-install --public-ip <LAN-IP>` |
| Relay bindet nicht | Port belegt (8099/8882/13478) | `ss -ltnp \| grep -E '8099\|8882'`; Ports in Einstellungen ändern |
| Plugin lädt nicht | Manifest/Import-Fehler | `hermes plugins doctor iwfcam4hermes`, `hermes plugins validate <dir>` |
| Kamera-UID taucht doppelt auf | alt: `ZIOTA_x` vs `x` | seit 0.8.x normalisiert; ggf. Relay neu starten |
| Vorschau ruckelt | FPS/Qualität zu hoch, CPU | `relay_fps`/`relay_quality` senken |

## Logs & Ablagen

| Was | Wo |
| --- | --- |
| Relay (Signaling, Motion, Watchdog, Fehler) | `journalctl --user -u iwfcam4hermes-relay.service` |
| Gateway (Plugin-Tools, Desktop-API) | `journalctl --user -u hermes-gateway.service` |
| Dashboard | `journalctl --user -u hermes-dashboard.service` |
| Desktop | `~/.hermes/logs/desktop.log` |
| Kamera-Config | `~/.hermes/iwfcam4hermes/config.json` (`.bak`) |
| Snapshots | `~/.hermes/iwfcam4hermes/snapshots/<uid>/` (+ `motion/`) |
| Relay-Unit | `~/.config/systemd/user/iwfcam4hermes-relay.service` |

## Sauberer Neustart

```bash
systemctl --user restart iwfcam4hermes-relay.service
systemctl --user restart hermes-gateway.service
systemctl --user restart hermes-dashboard.service
# Desktop danach neu starten (Ticket-Bootstrap)
```

Nach einem Plugin-Update zusätzlich:

```bash
hermes plugins install sademardotDE/iwfcam4hermes --force --yes-deps
hermes cameras relay-install --public-ip <LAN-IP>
```

Weiter: [API.md](API.md) · [CONFIGURATION.md](CONFIGURATION.md) ·
[MOTION.md](MOTION.md) · [SECURITY.md](SECURITY.md)
