# iwfcam4hermes Plugin

Hermes-Plugin für WiFi-Überwachungskameras (iWFCam & Z-IOT/X5).

**Stand 0.3.0 — als Hermes-Plugin lauffähig.** Das Verzeichnis ist ein natives
Hermes-Verzeichnis-Plugin (`plugin.yaml` + `__init__.py:register(ctx)`) und
registriert 13 Tools, die `hermes cameras …`-CLI, einen Dashboard-Tab und eine
Desktop-Seite. Zusätzlich lässt sich der Z-IOT-Protokoll-Stack (Signalisierung,
STUN, RTP/JPEG) sowie die Kamera-GUI standalone nutzen.

## Installation in Hermes

```bash
# Verzeichnis-Plugin in das Hermes-Home kopieren (oder verlinken):
cp -r iwfcam4hermes ~/.hermes/plugins/
hermes plugins enable iwfcam4hermes
hermes gateway restart   # bzw. Hermes neu starten

# Alternative: aus einem Git-Repo/einer URL installieren (sobald 0.3.0 gepusht ist)
hermes plugins install sademardotDE/iwfcam4hermes
```

Prüfen, ob Hermes das Plugin akzeptiert:

```bash
hermes plugins validate /pfad/zu/iwfcam4hermes
hermes plugins list                      # Status "enabled", 13 Tools
hermes cameras list                      # Plugin-CLI
```

Benötigtes Python-Paket: `requests` (über `python_dependencies` in
`plugin.yaml` deklariert). Optional: `websocket-client` für den Legacy-App-
WebSocket-Kanal, `opencv-python`/`pillow`/`tkinter` für die GUI, `bleak` für
BLE-Provisioning.

## Hermes-Tools

| Tool | Zweck |
| --- | --- |
| `camera_list` | konfigurierte Kameras auflisten |
| `camera_get` | Details einer Kamera |
| `camera_add` / `camera_update` / `camera_remove` | Kameras anlegen, ändern, löschen (schreibt die JSON-Konfiguration) |
| `camera_test` | Erreichbarkeit prüfen (TCP `host:port`) |
| `camera_stream_url` / `camera_snapshot_url` | Stream-/Snapshot-URL ableiten |
| `camera_snapshot` | Snapshot als JPEG speichern |
| `camera_signaling_login` | verifizierter Z-IOT-Login (TCP 8882) → Relay/STUN |
| `camera_receiver_start` / `_stop` / `_status` | selbstgehosteter Empfänger (Signalisierung + STUN + RTP/JPEG) |
| `camera_sources` | lokale Videoquellen (V4L2/Webcam/GStreamer) |
| `services_status` | Status von Samba (`smb`, `nmb`) und MiniDLNA |
| `services_start` / `services_stop` | Dienste starten/stoppen |
| `services_enable` / `services_disable` | Autostart (systemctl enable/disable) schalten |

CLI-Äquivalent (registriert als `hermes cameras`):

```bash
hermes cameras list
hermes cameras show cam1
hermes cameras stream-url cam1
hermes cameras snapshot cam1 --output /tmp/cam1.jpg
hermes cameras signaling-login ZIOTA_ABCDEFGHIJ
hermes cameras receiver-start --public-ip 192.168.0.10
hermes cameras receiver-status
hermes cameras services-status
hermes cameras services-enable smb
hermes cameras add --json '{"id":"cam4","name":"Garten","type":"iwfcam","host":"192.168.0.60","port":8080}'
hermes cameras update cam4 --json '{"port":554,"relay_mode":true}'
hermes cameras test cam4
hermes cameras remove cam4
```

## Einrichten im Dashboard

Der Dashboard-Tab **Kameras** (`/iwfcam`) ist die Einrichtungsoberfläche:

- **Kameras**: „+ Neue Kamera“ öffnet ein Formular (ID, Name, Typ, UID, Host,
  Port, Benutzer, Passwort, Kanal, Stream-/Snapshot-Pfad, Relay/Mock, Notizen).
  Jede Zeile hat **Snapshot**, **Test**, **Bearbeiten**, **Löschen**.
- **Dienste**: Samba (`smb`/`nmb`) und MiniDLNA mit Status (läuft/gestoppt,
  Autostart) und Buttons **Starten/Stoppen** sowie **Autostart an/aus**
  (systemctl, per sudo).
- Geschrieben wird nach `<Hermes-Home>/iwfcam4hermes/config.json` (bei Profilen
  das gemeinsame Basis-Home), atomar mit `.bak`-Sicherung; beim ersten Speichern
  wird die Datei aus `config.example.json` angelegt.
- Dieselben Operationen gibt es als Agent-Tools (`camera_add`, `camera_update`,
  `camera_remove`, `camera_test`, `services_*`) und als
  `hermes cameras …`-CLI.

## Konfiguration

Kamera-Geräte stehen in einer JSON-Datei; Auflösungsreihenfolge:

1. Tool-Argument `config` bzw. CLI-Option `--config`
2. Plugin-Einstellung `config` (Hermes → Plugins → iwfcam4hermes)
3. `<Hermes-Root>/iwfcam4hermes/config.json` (bei Profilen das gemeinsame
   Basis-Home; wird beim ersten Anlegen/Speichern automatisch erstellt)
4. `config.json` im Plugin-Verzeichnis
5. mitgeliefertes `config.example.json` (3 Beispielgeräte, eines davon `mock`)

Format (siehe `config.example.json`):

```json
{"devices": [{"id": "cam1", "name": "Wohnzimmer", "type": "iwfcam",
              "host": "192.168.1.50", "port": 554,
              "username": "admin", "password": "…",
              "channel": 0, "stream_path": "/live", "snapshot_path": "/snapshot",
              "relay_mode": false, "mock": false}]}
```

`type` ist `iwfcam`, `ziota` oder `pppp`. Snapshot-Verzeichnis und
Empfänger-Ports sind ebenfalls über die Plugin-Einstellungen konfigurierbar
(`snapshot_dir`, `signaling_host`, `signaling_port`, `public_ip`, `media_port`,
`stun_port`).

## Standalone-Nutzung

```bash
# CLI (Konfiguration explizit)
python3 -m iwfcam4hermes.plugin list --config iwfcam4hermes/config.example.json
python3 -m iwfcam4hermes.plugin signaling-login --uid ZIOTA_ABCDEFGHIJ
python3 -m iwfcam4hermes.plugin receiver --public-ip 192.168.0.10 --snapshots ./snapshots

# Plugin-Fassade (Kameras + Dienste)
python3 -m iwfcam4hermes.hermes_plugin            # Status + Geräte
python3 -m iwfcam4hermes.hermes_plugin cfg.json

# Tests (57 Tests, ohne Kamera/Netz)
python3 -m pytest iwfcam4hermes -q
# Falls ein global installiertes pytest-Plugin (z. B. syrupy) stört:
python3 -m pytest iwfcam4hermes -q -p no:syrupy
```

### Selbstgehosteter Empfänger (open-ziot-Ansatz)

`ziot_receiver.py` nimmt eine Kamera auf, die per BLE (z. B. mit der open-ziot
Android-App) auf **diesen** Host umgebogen wurde:

```bash
python3 -m iwfcam4hermes.ziot_receiver \
    --public-ip <LAN-oder-öffentliche-IPv4> \
    --signaling-port 8882 --media-port 10000 --stun-port 13478 \
    --snapshots ./snapshots --dht ref.jpg
```

- **Signalisierung** (TCP): Login `0x1`→`0x8000`, Zeit `0x21`→`0x8021`, Ready `0x2`,
  danach `0x9003` (Media-Ziel) + `0x8005` + Keepalive `0x8002`
- **STUN** (UDP): RFC 5389 Binding-Response mit XOR-MAPPED-ADDRESS
- **Media** (UDP): RTP/JPEG (PT26) → JPEG-Frames, PCMU (PT0) Audio
- Getestet mit simulierter Kamera (`test_ziot_receiver.py`), ohne Hardware

## Verifiziertes Z-IOT-Protokoll (Kurzfassung)

- Binäres `86 86`-Frame-Format, TCP-Port **8882**
- Login (`cmd 0x0001`, Firmware-String) → Server-Antwort `0x8000` live bestätigt
  (`sig.gps555.net`, `ipc.gps555.net`, `ipc.gps666.net`)
- Reply: `relay_ip:554`, `media_port 10000`, `stun.gps555.net:13478`, `cloud:8885`
- Implementierung: `ZIOTAdapter.signaling_login()` in `ziota_adapter.py`
- Vollständige Doku: [`docs/PROTOCOL.md`](docs/PROTOCOL.md)

Reproduzieren:

```bash
python3 -c "from iwfcam4hermes.ziota_adapter import ZIOTAdapter; print(ZIOTAdapter('ZIOTA_ABCDEFGHIJ').signaling_login('sig.gps555.net', 8882))"
```

Noch offen: Media-Framing nach Relay-Connect (braucht echte Kamera am Relay),
App-JSON-`Register`-Signatur, REST-Request-Signer — dokumentiert in §8 von
`docs/PROTOCOL.md`.

## BLE-Provisioning

`provision_ble.py` überträgt Wi-Fi-Zugang und Server-Endpunkt per Bluetooth
an die Kamera (Host mit BlueZ und `bleak`) — Anleitung:
[`docs/BLE_PROVISIONING.md`](docs/BLE_PROVISIONING.md).

```bash
python3 -m iwfcam4hermes.provision_ble --help
```

Im Container ohne Bluetooth nicht möglich; `--dry-run` baut nur das Paket.

## Kamera-GUI

`camera_gui.py` ist eine Tkinter-GUI (V4L2/RTSP/GStreamer/Webcam). Sie braucht
eine Desktop-Sitzung sowie `opencv-python`, `pillow` und `tkinter`:

```bash
python3 camera_gui.py
# oder aus dem Plugin:
python3 -c "from iwfcam4hermes.camera_gui_plugin import create_camera_gui_plugin as c; print(c().launch())"
```

Fehlende Voraussetzungen werden als klare Fehlermeldung gemeldet (kein
stiller Subprozess-Fehlschlag).

## AP-Modus: Live-Bild ohne Cloud (verifiziert)

Eine Kamera ohne gespeichertes WLAN (frisch eingeschaltet/resettet) spannt ihr
eigenes **offenes** WLAN `ZIOTA_<id>` (2,4 GHz) auf und ist lokal direkt
erreichbar — ohne Hersteller-Cloud und ohne BLE:

```bash
# 1. Mit dem Kamera-AP verbinden (offen), Client bekommt 192.168.1.100/24
nmcli dev wifi connect "ZIOTA_196758286858"
# 2. RTSP-URL über den Kontrollport TCP 8266 abfragen
python3 - <<'PY'
import socket
s = socket.create_connection(("192.168.1.1", 8266), timeout=5)
s.sendall(bytes.fromhex("8686000900010004000201010e0d"))
print(s.recv(4096))
# -> ... rtsp://192.168.1.1:7070/webcam/jpeg_dvp ...
PY
# 3. Live-Frame holen (UDP, TCP wird von der Kamera abgelehnt)
ffmpeg -rtsp_transport udp -i rtsp://192.168.1.1:7070/webcam/jpeg_dvp -frames:v 1 snap.jpg
```

Live verifiziert: MJPEG (yuvj420p) + PCM µ-law, 640×480 bzw. 240×320.
Details in [`docs/PROTOCOL.md`](docs/PROTOCOL.md) §2.6.

## Bekannte Einschränkungen

- Im **Station-Modus** (Kamera im Heim-WLAN) ist die Kamera **nicht** per
  RTSP/ONVIF erreichbar: Kamera → Signalisierung (TCP 8882, binär) →
  Relay/STUN → Media-Relay. Im **AP-Modus** dagegen liefert die Kamera ihre
  RTSP-URL über TCP 8266 (siehe oben) — für einen echten Stream ohne Cloud
  reicht das bereits.
- `libZGP2PComm.so` ist ARM64; auf x86_64 läuft nur der Stub-Fallback.
  Bibliothekspfad per `$IWFCAM_LIB` oder `so/lib/arm64-v8a/` im Plugin-Dir.
- BLE-Provisioning: In der aktuellen Kamera-Firmware war das Provisioning-GATT
  (`3600…`) nicht auflösbar; der AP-Modus (TCP 8266 → RTSP) ist der zuverlässige
  Weg zum Live-Bild. BLE braucht ohnehin einen Host mit Bluetooth (nicht im Container).
- Dashboard/Desktop-Seite benötigen die jeweilige Hermes-Desktop-Version; die
  Agent-Tools funktionieren unabhängig davon.

## Verzeichnisstruktur

```
iwfcam4hermes/
├── plugin.yaml            - Hermes-Manifest (Manifest v2, provides_tools/config_schema)
├── plugin.json            - Agent-Plugins-v1-Manifest (portable Metadaten)
├── __init__.py            - register(ctx): Tools + CLI
├── plugin_tools.py        - Tool-Schemas, Handler, `hermes cameras`
├── plugin.py              - Kamera-Modell, Konfiguration, Snapshot, Standalone-CLI
├── manager.py             - CameraManager
├── hermes_plugin.py       - Objekt-Fassade (Kameras + Dienste)
├── services.py            - Samba-/MiniDLNA-Steuerung (systemd)
├── camera_gui.py          - Tkinter-GUI (V4L2/RTSP/GStreamer)
├── camera_gui_plugin.py   - GUI-Wrapper (launch/stop/status/list_sources)
├── ziota_adapter.py       - Z-IOT-Adapter (Signalisierung + WebSocket-Scaffold)
├── ziot_receiver.py       - selbstgehosteter Empfänger (Signalisierung+STUN+RTP)
├── rtp_receiver.py        - RTP-Parser + RFC-2435-JPEG-Reassembly
├── media_receiver.py      - UDP-MediaReceiver (Frames, Snapshots, Audio)
├── provision_ble.py       - BLE-Provisioning
├── iwfcam_adapter.py      - iWFCam/JNI-Adapter (Stubs)
├── iwfcam_p2p.py          - P2P-High-Level-API
├── iwfcam_jni_stubs.py    - 271 JNI-Funktionen aus libZGP2PComm.so
├── stream_proxy.py        - HTTP/RTSP-Stream-Proxy
├── stun_client.py         - STUN-Client (RFC 5389)
├── pppp_adapter.py        - PPPP-Protokoll-Adapter
├── msg_analyzer.py        - Nachrichtenanalyse
├── dashboard/             - Dashboard-Tab + API-Backend
├── desktop/plugin.js      - Desktop-Seite
├── docs/                  - PROTOCOL.md, BLE_PROVISIONING.md
├── config.example.json    - Beispielkonfiguration
├── jpeg-huffman.bin       - Standard-Huffman-Tabellen (DHT) fürs JPEG-Decoding
└── test_*.py              - 57 Tests (Protokoll, RTP, Receiver, Plugin-Vertrag)
```

## Änderungsprotokoll

- **0.4.0:** Einrichtung im Dashboard: Kameras anlegen/ändern/löschen/testen, Samba/MiniDLNA starten/stoppen + Autostart; schreibbarer Konfigurations-Store (`config_store.py`), neue Tools/CLI-Befehle.
- **0.3.0:** Z-IOT-Signalisierung/Receiver, RTP/JPEG, BLE-Provisioning; **jetzt
  natives Hermes-Plugin** (`plugin.yaml`, `register(ctx)`, 13 Tools, CLI,
  Dashboard/Desktop), Samba/MiniDLNA-Steuerung eingebunden.
- **0.2.4:** Test 192.168.0.157 — keine Kamera-Ports offen, 0 Kameras im LAN.
- **0.2.3:** Netzwerktests 192.168.0.134 und 192.168.0.246.
- **0.2.2:** Plugin-`$schema` auf Agent-Plugins-v1 korrigiert.
- **0.2.1:** Dokumentation: lokale Kameras nicht per RTSP/ONVIF erreichbar.
- **0.2.0:** Erster Release mit GUI, JNI-Stubs, PPPP-Adapter.

## Kontakt

- GitHub: <https://github.com/sademardotDE/iwfcam4hermes>
- Doku: `docs/`
- Lizenz: MIT (siehe `plugin.json`)
