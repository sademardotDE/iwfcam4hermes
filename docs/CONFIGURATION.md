# Konfiguration — iwfcam4hermes

Version 0.17.0 · Stand 16.11.2026

Es gibt zwei Ebenen:

1. **Plugin-Einstellungen** (Hermes → Plugins → iwfcam4hermes) — Relay, Kamera-Config-Pfad,
   Snapshots, Motion, Watchdog. Sie landen in `plugins.entries.iwfcam4hermes.settings`
   der Hermes-Config (`~/.hermes/config.yaml` bzw. Profil-Config).
2. **Kamera-Konfiguration** (`config.json`) — die Geräte selbst plus der gemerkte
   `provision`-Block.

## Plugin-Einstellungen

| Schlüssel | Typ | Default | Bedeutung |
| --- | --- | --- | --- |
| `config` | str | `""` | Pfad zur Kamera-Config; leer = Standardauflösung (siehe unten) |
| `snapshot_dir` | str | `""` | Snapshot-Ablage; leer = `<Hermes-Root>/iwfcam4hermes/snapshots` |
| `signaling_host` | str | `sig.gps555.net` | Cloud-Signalisierung (nur für Tests/Login-Referenz) |
| `signaling_port` | int | `8882` | Port der Signalisierung (Relay/Cloud) |
| `public_ip` | str | `""` | LAN-IPv4 des Hosts für Provisionierung/Empfänger |
| `media_port` | int | `10000` | Basis-Media-Port (Relay vergibt **pro Kamera** einen ephemeren Port) |
| `stun_port` | int | `13478` | STUN-Port |
| `relay_public_ip` | str | `""` | Relay-Adresse, die Kameras bekommen (`hermes cameras relay-install --public-ip …`) |
| `relay_http_host` | str | `127.0.0.1` | Bind-Adresse der HTTP-Vorschau (Loopback empfohlen) |
| `relay_http_port` | int | `8099` | HTTP-Port der Vorschau/API |
| `relay_quality` | str | `medium` | Default-Qualität: `original`, `high`, `medium`, `low` |
| `relay_fps` | int | `5` | Default-FPS für MJPEG-Stream |
| `relay_max_cameras` | int | `16` | max. gleichzeitig bediente Kameras |
| `relay_snapshot_interval` | int | `60` | Sekunden zwischen Ringpuffer-Snapshots |
| `relay_snapshot_retain` | int | `200` | max. Snapshots pro Kamera |
| `relay_watchdog` | bool | `false` | Opt-in: offline Kameras automatisch provisonieren |
| `relay_watchdog_interval` | int | `300` | Prüfintervall (s) |
| `relay_watchdog_cooldown` | int | `1800` | Cooldown pro Kamera (s) |
| `relay_motion` | bool | `false` | Opt-in: Bewegungsmelder |
| `relay_motion_sensitivity` | int | `50` | Empfindlichkeit 1–100 (höher = empfindlicher) |
| `relay_motion_cooldown` | int | `10` | Mindestabstand zwischen Ereignissen (s) |
| `relay_motion_snapshot` | bool | `true` | Bewegungs-Snapshot unter `<uid>/motion/` ablegen |
| `relay_motion_webhook` | str | `""` | **ein** Webhook-Ziel (URL) |
| `relay_motion_webhooks` | str | `""` | **mehrere** Ziele, eine Zeile pro Webhook (`typ\|url`) |
| `relay_motion_photo` | bool | `true` | Bei Telegram Bild mitsenden |
| `relay_motion_photo_mode` | enum | `document` | `document` = Originaldatei (beste Qualität), `photo` = inline/komprimiert |
| `relay_motion_display` | bool | `false` | Bewegungsbild auf dem USB-Smart-Dashboard anzeigen |
| `relay_motion_display_duration` | int | `8` | Anzeigedauer des Bildes auf dem USB-Display (s) |

Änderungen an Relay-relevanten Einstellungen brauchen
`hermes cameras relay-install --public-ip <LAN-IP>` (schreibt die Unit neu und
startet den Dienst); Motion/Watchdog greifen danach sofort.

## Kamera-Konfiguration (`config.json`)

Auflösungsreihenfolge:

1. Tool-Argument `config` / CLI `--config`
2. Plugin-Einstellung `config`
3. `IWFCAM_CONFIG` (Env)
4. `<Hermes-Root>/iwfcam4hermes/config.json` (bei Profilen: gemeinsames Basis-Home)
5. `config.json` im Plugin-Verzeichnis
6. mitgeliefertes `config.example.json` (nur lesen; beim ersten Speichern wird
   eine beschreibbare Datei unter 4. angelegt)

Format:

```json
{
  "devices": [
    {
      "id": "ziota-196758286858",
      "name": "ZIOTA 196758286858",
      "type": "iwfcam",
      "uid": "ZIOTA_196758286858",
      "host": null,
      "port": null,
      "username": null,
      "password": null,
      "channel": 0,
      "stream_path": "/webcam/jpeg_dvp",
      "snapshot_path": "/snapshot",
      "relay_mode": true,
      "notes": "Relay-Stream (Kamera 192.168.0.246)",
      "mock": false
    }
  ],
  "provision": {
    "ssid": "cccp4ever",
    "password": "…",
    "server_ip": "192.168.0.4",
    "server_port": 8882,
    "utc_offset": 60
  }
}
```

| Feld | Bedeutung |
| --- | --- |
| `id` | stabile ID (`[A-Za-z0-9_.-]{1,64}`) |
| `name` | Anzeigename |
| `type` | `iwfcam`, `ziota`, `pppp` |
| `uid` | Kamera-UID (mit/ohne `ZIOTA_`-Präfix; intern normalisiert) |
| `host`/`port` | direkter RTSP-/HTTP-Endpunkt (z. B. AP-Modus `192.168.1.1:7070` oder LAN-IP) |
| `relay_mode` | `true`: Vorschau/Snapshot bevorzugt über den Relay, mit Fallback auf `host`/`port` |
| `stream_path`/`snapshot_path` | Pfade für URL-Ableitung |
| `mock` | erzeugt ein Platzhalterbild (Tests) |
| `provision` | gemerkte WLAN-/Relay-Daten für Reconnect/Watchdog (Datei `0600`) |

Schreiben ist atomar (Temp-Datei + `os.replace`), mit `.bak` der Vorgängerversion.

## systemd-Unit (Relay)

Erzeugt von `relay_install` unter
`~/.config/systemd/user/iwfcam4hermes-relay.service`. Flags:

```
--public-ip <LAN-IP>
--signaling-port 8882 --media-port 10000 --stun-port 13478
--http-host 127.0.0.1 --http-port 8099
--quality medium --fps 5 --max-cameras 16
--snapshots <dir> --snapshot-interval 60 --snapshot-retain 200
[--watchdog --watchdog-interval 300 --watchdog-cooldown 1800]
[--motion --motion-sensitivity 50 --motion-cooldown 10] [--no-motion-snapshot]
[--motion-webhook "typ|url"] … [--no-motion-photo] [--motion-photo-mode document|photo]
[--motion-display --motion-display-duration 8]
```

## Umgebungsvariablen

| Variable | Zweck |
| --- | --- |
| `IWFCAM_CONFIG` | Pfad zur Kamera-Config (überschreibt Standard) |
| `IWFCAM_LIB` | Pfad zu `libZGP2PComm.so` (ARM-Adapter, optional) |
| `IWFCAM_PUBLIC_IP` | Default für `--public-ip` (Relay-CLI) |
| `IWFCAM_BLE_PYTHON` | Interpreter mit `bleak` für den BLE-Scan-Fallback |
| `HERMES_HOME` | Hermes-Home/Profil (Config-Auflösung) |

## USB-Smart-Dashboard (Display)

Die Anbindung ist eine **Datei-Bridge**, kein eigener Treiber:

- Erkennung: Plugin-Verzeichnis `plugins/usb-smart-dashboard` + `plugins.enabled`
  in einem Hermes-Home; Anzeige: `/dev/ttyACM*`/`/dev/ttyUSB*` oder laufender
  `usb-smart-dashboard.service`.
- Bild: `<Hermes-Root>/usb-smart-dashboard/show-image.jpg` +
  `show-image.json` (`created`, `duration`, `source`).
- Der aktive Renderer des USB-Plugins zeigt das Bild skaliert (480×320) und
  fällt nach Ablauf auf die Live-Statistik zurück.
- Deaktivieren: `relay_motion_display=false` (oder USB-Plugin deaktivieren).

## Profile & Ablage

- Kamera-Config: bei Profilen **gemeinsames Basis-Home** (`~/.hermes/iwfcam4hermes/config.json`),
  nicht pro Profil — Kameras sind hostweit.
- Plugin-Einstellungen: pro Profil (`plugins.entries.iwfcam4hermes.settings`).
- Snapshots: `snapshot_dir` (Default hostweit).
- Relay-Unit: User-spezifisch (`~/.config/systemd/user/`).

## Sicherheit

- `config.json` enthält Kamera-Passwörter und WLAN-Zugangsdaten (Rechte `0600`).
- Webhook-URLs können Tokens enthalten (Telegram-Bot-Token, Slack-Secret); sie
  stehen in `config.yaml`/der Unit. Details: [SECURITY.md](SECURITY.md).

Weiter: [API.md](API.md) · [MOTION.md](MOTION.md) ·
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) · [ARCHITECTURE.md](ARCHITECTURE.md)
