# Architektur — iwfcam4hermes

Version 0.17.0 · Stand 16.11.2026

Dieses Dokument beschreibt, wie die Teile des Plugins zusammenspielen: Kameras,
Relay-Dienst, Bewegungsmelder, Watchdog, HTTP-API und die beiden Oberflächen
(Dashboard-Tab und Hermes-Desktop-Seite).

## Überblick

```
  Kamera A ─┐   TCP 8882 (Signalisierung, binär)        ┌──────────────────────────┐
  Kamera B ─┤   UDP 13478 (STUN)                        │  relay.py (systemd-User) │
            ├──► UDP <port pro Kamera> (RTP/JPEG+PCMU) ─►│  ZiotReceiverServer       │
  Kamera N ─┘                                          │  ├ MediaHub (1 Receiver/   │
                                                        │  │   Kamera, eigener Port)│
                                                        │  ├ MotionHub (optional)   │
                                                        │  ├ SnapshotStore          │
                                                        │  └ CameraWatchdog (opt-in)│
                                                        └──────────┬───────────────┘
                                                                   │ HTTP 127.0.0.1:8099
                          ┌────────────────────────────────────────┼─────────────────────────┐
                          │                                        │                         │
                 Dashboard-Tab /iwfcam                  Hermes-Desktop-Seite /iwfcam    Webhooks
               (plugin_api.py im Dashboard)            (desktop/plugin.js via Gateway)  (Telegram,
                          │                                        │                    Slack, …)
                          └───────────────► Agent-Tools/CLI ◄──────┘
                                     (camera_*, relay_*, hermes cameras …)
```

## Komponenten

| Datei | Rolle |
| --- | --- |
| `relay.py` | Relay-Dienst: Signalisierung, STUN, Media-Empfang, HTTP-Vorschau, Snapshots, Motion, Watchdog, Systemd-Unit |
| `ziot_receiver.py` | Kameraseitige Protokollschicht: Login-Reply `0x8000`, Zeit/Ready/Keepalive, Media-Ziel `0x9003`, `MediaHub` (ein UDP-Port je Kamera), Session-/Zustandserkennung |
| `rtp_receiver.py` / `media_receiver.py` | RTP-Parser, RFC-2435-JPEG-Reassembly, PCMU-Audio, Frame-Statistik |
| `motion.py` | Bewegungsmelder (Graustufen-Differenz), Ereignis-Ringpuffer, Webhook-Versand (typisiert) |
| `display.py` | USB-Smart-Dashboard-Erkennung + Bild-Bridge (`show-image.jpg`/`show-image.json`) |
| `watchdog.py` | Opt-in: offline Kameras mit sichtbarem ZIOTA-AP automatisch neu provisionieren |
| `provision.py` | AP-Provisionierung (TCP 8266), inkl. Statik-IP-Fallback ohne DHCP |
| `provision_ble.py` | BLE-Provisionierung (bluez/bleak; bei `TXW817_D` ohne GATT-Services) |
| `autoconf.py` | Kameras finden: WLAN-AP, BLE-Advertising, aktueller AP + RTSP |
| `config_store.py` | Schreibbarer Kamera-Config-Store (`config.json`, atomar, `.bak`, `0600`) |
| `plugin_tools.py` | 25 Agent-Tools + `hermes cameras …`-CLI |
| `plugin.py` / `manager.py` | Kamera-Modell, Snapshot-/Stream-URLs, Konfigurationsverwaltung |
| `dashboard/` | Dashboard-Tab `/iwfcam` (manifest, API-Backend, UI-Bundle) |
| `desktop/plugin.js` | Hermes-Desktop-Seite `/iwfcam` (gleiche API über `ctx.rest`) |

## Ports

| Zweck | Proto | Default | Konfigurierbar über |
| --- | --- | --- | --- |
| Signalisierung (Kamera → Relay) | TCP | 8882 | `signaling_port` / `--signaling-port` |
| STUN | UDP | 13478 | `stun_port` / `--stun-port` |
| Media pro Kamera | UDP | **ephemer** | automatisch pro Login (`MediaHub`) |
| HTTP-Vorschau/API | TCP | 8099 (nur `127.0.0.1`) | `relay_http_port`, `relay_http_host` |
| Dashboard/Desktop-API | TCP | Dashboard-Port (Default 9119) | Hermes-Dashboard |

Der Relay bindet standardmäßig nur an **Loopback** für HTTP. Signalisierung und
STUN müssen für Kameras im LAN erreichbar sein (`relay_public_ip`).

## Datenfluss einer Kamera

1. **Provisionierung** (AP-Modus oder BLE): Kamera erhält SSID/Passwort,
   Relay-Adresse `ip:8882`, UTC-Offset und Registrierungscode.
2. **Login:** Kamera öffnet TCP 8882, sendet `cmd 0x0001` mit UID/Firmware.
   Der Relay legt einen `MediaReceiver` mit eigenem UDP-Port an und antwortet mit
   `0x8000` (Relay-IP, Media-Port, STUN).
3. **Media-Ziel:** Nach Zeit/Ready sendet der Relay `0x9003` mit `ip:media_port`
   und hält die Verbindung mit Keepalives (`0x8002`) offen.
4. **Frames:** Kamera sendet RTP/JPEG (PT26, `ssrc` pro Kamera) und PCMU (PT0).
   Der Receiver reassembliert JPEGs und aktualisiert `frames`, `width/height`,
   `last_frame_age_s`.
5. **Zustand:** `streaming` (Frame ≤ 5 s), `paused` (Signalisierung lebt, aber
   keine frischen Frames), `offline` (keine Session). Jeder Signaling-Frame
   aktualisiert `last_seen`; dadurch bleibt eine nur pausierende Kamera
   `paused` statt fälschlich `offline`.
6. **Weiterverarbeitung:** HTTP-Vorschau (Snapshot/Stream, Qualität/FPS),
   `SnapshotStore` (Ringpuffer), `MotionHub` (optional), `CameraWatchdog`
   (optional), Webhooks (optional).

## Persistenz

| Daten | Ort | Hinweise |
| --- | --- | --- |
| Kamera-Konfiguration | `<Hermes-Root>/iwfcam4hermes/config.json` | atomar, `.bak`, Rechte `0600`; enthält auch den `provision`-Block (WLAN-Zugangsdaten, Relay-Endpunkt) |
| Snapshots (Ringpuffer) | `<snapshot_dir>/<uid>/<YYYYmmdd-HHMMSS>.jpg` | Default `~/.hermes/iwfcam4hermes/snapshots`; 60 s / 200 pro Kamera |
| Bewegungs-Snapshots | `<snapshot_dir>/<uid>/motion/*.jpg` | max. 200 pro Kamera, unabhängig vom Ringpuffer gezählt |
| USB-Display-Inbox | `<Hermes-Root>/usb-smart-dashboard/show-image.{jpg,json}` | Bewegungssnapshot für das USB-Smart-Dashboard; wird vom aktiven Renderer (Gateway-Thread oder `standalone.py`) gelesen |
| Relay-Unit | `~/.config/systemd/user/iwfcam4hermes-relay.service` | von `relay_install` erzeugt; Flags spiegeln die Plugin-Einstellungen |
| Motion-Ereignisse | nur im Speicher (Relay) | Ringpuffer 50/Kamera; nach Relay-Neustart leer |

## Prozessmodell

- **`iwfcam4hermes-relay.service`** (systemd --user): Relay, Snapshots, Motion,
  Watchdog. Läuft unabhängig von Hermes-Sessions.
- **Hermes-Gateway**: lädt das Plugin (Tools/CLI) und stellt die
  Desktop-Seite/Plugin-API bereit.
- **Hermes-Dashboard** (`hermes-dashboard.service`): hostet den Tab `/iwfcam`
  und `dashboard/plugin_api.py`.
- **USB-Smart-Dashboard** (separates Plugin): eigener Renderthread im Gateway
  und/oder `usb-smart-dashboard.service` (`standalone.py`); beide lesen die
  gemeinsame Bild-Inbox.
- **Hermes Desktop**: lädt `desktop/plugin.js` aus
  `<Hermes-Root>/desktop-plugins/iwfcam4hermes/` (Spiegel von `desktop/`).

## Fehlerverhalten / Robustheit

- Snapshot-/Motion-Schreibfehler werden geloggt, stoppen aber keine Threads.
- Webhook-Versand läuft asynchron mit 5 s Timeout; Fehler nur im Log.
- Signalisierungs-Sessions werden bei Verbindungsabbau sauber entfernt;
  Media-Receiver bleiben für Zustandsanzeige/Snapshots erhalten.
- `relay_install` schreibt die Unit atomar (mit `.bak`) und aktiviert/startet sie.
- Der Watchdog provisioniert höchstens eine Kamera pro Lauf (Host-WLAN-Wechsel)
  und hält pro Kamera einen Cooldown ein.

Weiter: [API.md](API.md) · [CONFIGURATION.md](CONFIGURATION.md) ·
[MOTION.md](MOTION.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md) ·
[SECURITY.md](SECURITY.md)
