# API-Referenz — iwfcam4hermes

Version 0.17.0 · Stand 16.11.2026

Drei Schnittstellen greifen auf dasselbe Modell zu:

1. **Agent-Tools** (`camera_*`, `relay_*`) im Hermes-Gateway,
2. **CLI** `hermes cameras …` (gleiche Handler),
3. **HTTP**: Relay-API (`127.0.0.1:8099`) und Dashboard-Plugin-API
   (`/api/plugins/iwfcam4hermes`).

## Agent-Tools

`*` = Pflichtparameter. Alle Tools liefern JSON als String; Fehler als
`{"ok": false, "error": …}`.

| Tool | Parameter | Zweck |
| --- | --- | --- |
| `camera_list` | `config` | Kameras aus der Konfiguration |
| `camera_get` | `device_id*`, `config` | Details einer Kamera |
| `camera_stream_url` | `device_id*`, `config` | Stream-URL ableiten |
| `camera_snapshot_url` | `device_id*`, `config` | Snapshot-URL ableiten |
| `camera_snapshot` | `device_id*`, `output`, `config` | Snapshot als JPEG speichern |
| `camera_signaling_login` | `uid*`, `host`, `port`, `firmware`, `timeout` | Z-IOT-Login testen |
| `camera_receiver_start` | `public_ip`, `signaling_port`, `media_port`, `stun_port` | Empfänger starten (Standalone) |
| `camera_receiver_stop` / `_status` | – | Empfänger stoppen/Status |
| `camera_sources` | – | lokale Videoquellen (V4L2/Webcam/GStreamer) |
| `camera_add` | `device*`, `config` | Kamera anlegen |
| `camera_update` | `device_id*`, `changes*`, `config` | Kamera ändern |
| `camera_remove` | `device_id*`, `config` | Kamera löschen |
| `camera_test` | `device_id*`, `timeout`, `config` | TCP-Erreichbarkeit prüfen |
| `camera_autoconf` | `apply`, `mode` (`both`/`wifi`/`ble`), `config` | Kameras finden/anlegen |
| `camera_provision_wifi` | `camera_ssid`, `ssid*`, `password*`, `server_ip`, `server_port`, `utc_offset`, `auto_connect` | AP-Provisionierung (merkt WLAN-Daten) |
| `camera_reconnect` | `device_id*`, `camera_ssid`, `ssid`, `password`, `server_ip`, `server_port`, `utc_offset`, `auto_connect` | offline Kamera neu provisionieren |
| `camera_snapshots` | `uid`, `save` | Snapshot-Ringpuffer anzeigen/sofort speichern |
| `camera_motion` | `action` (`status`/`events`/`wait`/`test`), `uid`, `limit`, `timeout` | Bewegungsmelder |
| `camera_watchdog` | `action` (`status`/`run`) | Watchdog-Status/sofort prüfen |
| `relay_status` | – | Relay-Status inkl. `cameras`, `motion`, `watchdog`, `snapshots` |
| `relay_install` | `public_ip`, `signaling_port`, `media_port`, `stun_port`, `http_port`, `start` | Unit schreiben/aktivieren |
| `relay_start` / `relay_stop` / `relay_uninstall` | – | Dienststeuerung |

### CLI-Äquivalente

```bash
hermes cameras list|show|stream-url|snapshot-url|snapshot|add|update|remove|test
hermes cameras signaling-login <uid>
hermes cameras receiver-start|receiver-stop|receiver-status
hermes cameras sources
hermes cameras autoconf [--apply] [--mode wifi|ble|both]
hermes cameras wifi
hermes cameras provision --camera ZIOTA_… --ssid … --password … --server-ip …
hermes cameras reconnect <device_id>
hermes cameras snapshots [--uid …] [--save]
hermes cameras motion status|events|wait|test [--uid …] [--limit N] [--timeout S]
hermes cameras watchdog status|run
hermes cameras relay-install|relay-status|relay-start|relay-stop|relay-uninstall
```

## Relay-HTTP-API

Basis: `http://127.0.0.1:8099` (nur Loopback, keine Auth — lokal halten!).

| Methode | Pfad | Beschreibung |
| --- | --- | --- |
| GET | `/`, `/status` | JSON: Ports, Kameras (Zustand, Frames, Auflösung, `last_frame_age_s`), `totals`, `snapshots`, `motion`, `watchdog`, `pil` |
| GET | `/cameras` | wie `/status`, Fokus Kameraliste |
| GET | `/snapshot.jpg` | aktuelles JPEG; Query: `uid`, `quality` (`original/high/medium/low`) |
| GET | `/stream.mjpg` | MJPEG-Stream; Query: `uid`, `quality`, `fps` |
| GET | `/snapshots` | Snapshot-Ringpuffer: `dir`, `interval`, `retain`, `total`, `cameras` |
| POST | `/snapshots/save` | sofort speichern; Query: `uid` (optional) |
| GET | `/motion` | Bewegungsmelder: `enabled`, `sensitivity`, `threshold`, `cooldown`, `cameras`, `webhooks`, `webhook_count`, `photo_mode`; Query: `uid` |
| GET | `/motion/events` | letzte Ereignisse; Query: `uid`, `limit` |
| POST | `/motion/test` | Test-Benachrichtigung an alle Webhooks (mit aktuellem Frame) |
| GET | `/watchdog` | Watchdog-Status inkl. Aktionen/Cooldown |
| POST | `/watchdog/run` | sofortiger Prüflauf |

Beispiele:

```bash
curl -s http://127.0.0.1:8099/status | jq
curl -s -o /tmp/cam.jpg "http://127.0.0.1:8099/snapshot.jpg?uid=196758286858&quality=high"
curl -s "http://127.0.0.1:8099/motion/events?limit=5" | jq
curl -s -X POST http://127.0.0.1:8099/motion/test | jq
curl -s -X POST "http://127.0.0.1:8099/snapshots/save?uid=196758286858" | jq
```

## Dashboard-Plugin-API

Namespace `/api/plugins/iwfcam4hermes` (Auth über das Dashboard, Cookies/Session).

| Methode | Pfad | Beschreibung |
| --- | --- | --- |
| GET | `/config` | Pfad/Status der Kamera-Konfiguration |
| GET/POST | `/devices` | Liste/anlegen (JSON-Body wie `config.json`-Eintrag) |
| GET/PUT/DELETE | `/devices/{id}` | Detail/ändern/löschen |
| POST | `/devices/{id}/test` | Erreichbarkeit testen |
| POST | `/devices/{id}/reconnect` | Reconnect; erwartbare Fälle (`unavailable`) kommen als **200 mit Hinweis** |
| POST | `/devices/autoconf` | Scan (Body: `apply`, `mode`) |
| GET | `/stream-url/{id}`, `/snapshot/{id}` | URL/Snapshot als Data-URL; `?poll=1` liefert bei fehlendem Bild **200 + `image: null`** |
| GET | `/relay` | Relay-Status (Modul-Sicht, inkl. `motion`, `watchdog`) |
| POST | `/relay/{install|start|stop|uninstall}` | Dienstaktionen |
| GET | `/relay/snapshot` | Snapshot über den Relay (`uid`, `quality`) |
| GET | `/relay/snapshots`, POST `/relay/snapshots/save` | Snapshot-Ablage |
| GET | `/relay/motion`, `/relay/motion/events`, POST `/relay/motion/test` | Bewegungsmelder |
| GET | `/relay/watchdog`, POST `/relay/watchdog/run` | Watchdog |
| GET | `/wifi` | WLAN-Status + Kamera-APs |
| POST | `/provision` | Provisionierung (Body: `camera_ssid`, `ssid`, `password`, `server_ip`, …) |

## Antwortformate (Auszug)

```json
// /status (gekürzt)
{"ok": true, "cameras": [{"uid": "196758286858", "state": "streaming",
  "frames": 1234, "width": 640, "height": 480, "port": 47554,
  "connected": true, "last_frame_age_s": 0.1}],
 "totals": {"cameras": 2, "streaming": 1, "paused": 1, "offline": 0},
 "motion": {"enabled": true, "threshold": 0.0328, "webhook_count": 1},
 "watchdog": {"enabled": true, "interval": 300.0},
 "snapshots": {"enabled": true, "total": 400, "retain": 200}}
```

```json
// /motion/events
{"ok": true, "events": [{"uid": "196758286858", "ts": 1794861300.1,
  "score": 0.0812, "snapshot": "…/motion/20261116-215500.jpg"}]}
```

```json
// Tool-Fehler
{"ok": false, "error": "Kamera-AP ZIOTA_… nicht sichtbar — Kamera einschalten/aufwecken",
 "unavailable": true, "camera_aps": []}
```

Weiter: [CONFIGURATION.md](CONFIGURATION.md) · [MOTION.md](MOTION.md) ·
[ARCHITECTURE.md](ARCHITECTURE.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
