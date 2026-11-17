# USB-Smart-Dashboard-Anbindung — iwfcam4hermes

Version 0.18.0 · Stand 17.11.2026

Das Hermes-Plugin **`usb-smart-dashboard`** steuert ein USB-Display
(Turing Smart Screen 3.5", VID:PID `1a86:5722`, seriell `USB35INCHIPSV2`).
`iwfcam4hermes` kann den Bewegungs-Snapshot dorthin schicken — ohne eigenes
Serienprotokoll und ohne Cross-Plugin-Import. Die Übergabe läuft über die
**Bild-Inbox** des USB-Plugins.

## Voraussetzungen

- Hermes-Plugin `usb-smart-dashboard` **≥ 0.5.0** (Bild-Bridge).
- Plugin geladen: in einem Hermes-Home unter `plugins/usb-smart-dashboard`
  installiert und in `plugins.enabled` (oder `entries.…enabled`) aktiv.
- Display erreichbar: `/dev/ttyACM*`/`/dev/ttyUSB*` vorhanden **oder**
  `usb-smart-dashboard.service` aktiv.
- `iwfcam4hermes` ≥ 0.18.0.

## Erkennung

`display.py` prüft:

| Prüfung | Quelle |
| --- | --- |
| installiert | `<Hermes-Root>/**/plugins/usb-smart-dashboard/plugin.yaml` |
| geladen/aktiviert | `plugins.enabled` bzw. `plugins.entries.usb-smart-dashboard` in der jeweiligen Config |
| Version | `version:` aus `plugin.yaml` |
| Display verbunden | `/dev/ttyACM*`, `/dev/ttyUSB*` |
| Dienst | `systemctl --user is-active usb-smart-dashboard.service` |

Ergebnis (Auszug aus `GET /display` bzw. `camera_display status`):

```json
{"ok": true, "plugin": "usb-smart-dashboard", "loaded": true,
 "version": "0.5.0", "display_connected": true,
 "serial_ports": ["/dev/ttyACM0"], "service_active": true,
 "ready": true, "inbox": "~/.hermes/usb-smart-dashboard",
 "enabled": true, "duration": 8, "active_image": {"source": "motion:196758286858", "remaining": 6.2}}
```

- `loaded=false` → Option wird in der UI als „nicht geladen" angezeigt, Tests
  liefern einen klaren Hinweis.
- `ready` = geladen **und** (Display verbunden **oder** Dienst aktiv).

## Aktivieren

| Einstellung | Default | Bedeutung |
| --- | --- | --- |
| `relay_motion_display` | `false` | Bewegungsbild aufs Display schicken |
| `relay_motion_display_duration` | `8` | Anzeigedauer in Sekunden |

Danach `hermes cameras relay-install --public-ip <LAN-IP>` (Flags
`--motion-display --motion-display-duration 8`) und der Relay-Dienst startet neu.

## Ablauf

```
Kamera ──► Relay (MotionHub) ──► JPEG + Dauer
                                   │
                                   ▼
        <Hermes-Root>/usb-smart-dashboard/show-image.jpg
        <Hermes-Root>/usb-smart-dashboard/show-image.json
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   usb-smart-dashboard (Gateway-Thread)     standalone.py (systemd)
              └──────────────► Display 480×320 ◄────────┘
```

- `show-image.jpg` wird atomar geschrieben (`.tmp` + `os.replace`).
- `show-image.json`: `{"created": <epoch>, "duration": 8, "source": "motion:<uid>"}`.
- Der aktive Renderer zeigt das Bild einmal, skaliert es auf die Panelgröße
  (schwarze Ränder) und fällt nach Ablauf auf die Live-Statistik zurück.
- Nur **ein** Prozess besitzt das Panel (Advisory-Flock im USB-Treiber); die
  Inbox funktioniert mit beiden Renderern.

## Bedienung

```bash
hermes cameras display status     # geladen? Version, Display, aktives Bild
hermes cameras display test       # letztes Kamera-Frame aufs Display
curl -s http://127.0.0.1:8099/display | jq
curl -s -X POST http://127.0.0.1:8099/display/test | jq
```

Dashboard/Desktop: Relay-Karte zeigt die Zeile
„USB-Smart-Dashboard: geladen (0.5.0) · Display verbunden · Bewegungsbild an (8s)"
und bietet den Button **„Testbild auf Display"**.

## Manuell testen (ohne Bewegung)

```bash
# Snapshot holen und in die Inbox legen
curl -s -o /tmp/frame.jpg "http://127.0.0.1:8099/snapshot.jpg?uid=196758286858&quality=original"
python3 - <<'PY'
import json, os, time
from pathlib import Path
home = Path.home() / ".hermes" / "usb-smart-dashboard"
home.mkdir(parents=True, exist_ok=True)
(tmp := home / "show-image.jpg.tmp").write_bytes(Path("/tmp/frame.jpg").read_bytes())
os.replace(tmp, home / "show-image.jpg")
(home / "show-image.json").write_text(json.dumps(
    {"created": time.time(), "duration": 15, "source": "manual"}))
PY
journalctl --user -u usb-smart-dashboard.service -n 20 --no-pager | grep -i image
```

## Fehlersuche

| Symptom | Ursache / Lösung |
| --- | --- |
| `loaded=false` | USB-Plugin im aktiven Home nicht installiert/aktiviert → `hermes plugins list \| grep usb` |
| `display_connected=false` | Panel nicht angesteckt / anderer Port → `lsusb` (`1a86:5722`), `ls /dev/ttyACM*` |
| Test sagt „nicht geladen" | Erkennung findet kein Plugin in den Homes; USB-Plugin installieren |
| Bild erscheint kurz, dann Stats | normal — Dauer abgelaufen (`relay_motion_display_duration`) |
| Bild erscheint gar nicht | Inbox-Home ≠ Home des Renderers; `HERMES_HOME`, `show-image.json` prüfen |
| Display flackert/Streifen | anderer Prozess rendert parallel (Flock) — Dienst/Thread prüfen |

## Sicherheit & Datenschutz

- Das Bild liegt lokal in `<Hermes-Root>/usb-smart-dashboard/` und ist für
  Nutzer des Displays sichtbar.
- Keine Cloud, kein Netzwerkversand für das Display.
- Dateien nach Gebrauch nicht löschen, solange die Anzeige läuft; die
  Meta-Datei steuert die Restlaufzeit.

Weiter: [MOTION.md](MOTION.md) · [API.md](API.md) ·
[CONFIGURATION.md](CONFIGURATION.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
