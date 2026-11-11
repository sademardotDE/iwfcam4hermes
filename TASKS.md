# Aufgabenliste – iwfcam4hermes Plugin

## Phase 1: Grundgerüst ✅
- [x] Plugin-Struktur angelegt (`plugin.py`, `__init__.py`, `config.example.json`)
- [x] Camera/CameraType Datenmodelle
- [x] CLI (list, show, stream-url, snapshot-url, snapshot)
- [x] Z-IOT Adapter-Scaffold (`ziota_adapter.py`)
- [x] iWFCam Adapter-Scaffold (`iwfcam_adapter.py`)
- [x] JNI-Stubs generiert (`iwfcam_jni_stubs.py`)
- [x] Snapshot-Abruf via HTTP (`fetch_snapshot`)

## Phase 2: Z-IOT Protokoll ⭐ DURCHBRUCH (verifiziert)
- [x] WebSocket-Verbindung zu `ws.gps555.net:7080/ws` (HTTP 101 Upgrade bestätigt)
- [x] Kamera-Signalisierung entschlüsselt: binäres `86 86`-Frame-Format, Port **8882**
- [x] Login-Kommando `0x0001` (Firmware-String) → Server-Antwort `0x8000` LIVE verifiziert
- [x] Login-Reply dekodiert: relay_ip:554, media_port 10000, stun.gps555.net:13478, cloud:8885
- [x] `ziota_adapter.py` mit `signaling_login()` — 3/3 Signalisierungsserver erfolgreich
- [x] Frame-Parser + XOR-Checksumme + Sequenz-Zähler implementiert und getestet
- [x] STUN-Client (`stun.gps555.net:13478`) — öffentliche IP ermittelt
- [x] REST-API-Oberfläche (`ipc.gps555.net/api/v1/...`) kartiert (40+ Endpunkte, Bearer-Auth)
- [x] App-JSON-Vokabular aus `libapp.so` extrahiert (msgType/cmdType/deviceId/sequence)
- [x] Vollständige Protokoll-Doku: `docs/PROTOCOL.md`
- [x] Post-Login-Ablauf dokumentiert (open-ziot Referenz: 0x21/0x8021 Zeit, 0x02/0x8001 ACK, 0x9003 Media-Ziel, 0x8002 Keepalive, 0x8005 Retry)
- [x] RTP/JPEG-Decoder `rtp_receiver.py` (parse_rtp + RFC 2435 Reassembly, PT26 Video / PT0 PCMU)
- [x] UDP-`MediaReceiver` (`media_receiver.py`): bindet RTP-Port, Frames + Snapshots + Audio-Puffer
- [x] Selbstgehosteter Empfänger `ziot_receiver.py` (Signalisierung + STUN-Responder + Media, open-ziot-Ansatz) — E2E-Tests mit simulierter Kamera
- [x] BLE-Provisioning `provision_ble.py` (Paket-Builder + bleak-Writer) — Anleitung `docs/BLE_PROVISIONING.md`
- [x] Standard-DHT gebündelt (`jpeg-huffman.bin`, Standard-Huffman) — Frames dekodierbar ohne `--dht`
- [x] Echte Kamera-UIDs ermittelt: `ZIOTA_196758286858`, `ZIOTA_635572396930` (BLE-Advertising + AP-SSID)
- [x] **AP-Modus live verifiziert:** TCP 8266 mit `86 86 00 09 …` abfragen → RTSP-URL
      `rtsp://192.168.1.1:7070/webcam/jpeg_dvp` → MJPEG 640×480 / 240×320, echte Frames geholt
      (dokumentiert in `docs/PROTOCOL.md` §2.6)
- [x] Signalisierungs-Login mit echter UID gegen 3 Vendor-Server → Relay/STUN/Cloud
- [ ] BLE-Provisioning dieser Firmware: Provisioning-GATT (`3600…`) war nicht auflösbar
      (`ServicesResolved: yes` ohne Attribute) — offen; AP-Modus ist der verlässliche Live-Weg
- [ ] Live-Provisioning auf Host mit BlueZ ausführen (Container hat kein BLE)
- [ ] Live gegen echte Kamera: per BLE auf diesen Host umbiegen (selbstgehosteter Empfänger)
- [ ] App-JSON `Register`-Body + Signatur — nicht rekonstruiert (App-Kanal, für Steuerung nicht nötig)
- [ ] REST-Request-Signer (MD5 `_signPrefix`/`_signSuffix`) — nicht rekonstruiert

## Phase 3: Hermes-Integration ✅ (lauffähig)
- [x] Natives Verzeichnis-Plugin: `plugin.yaml` (Manifest v2) + `__init__.py:register(ctx)`
- [x] 13 Hermes-Tools registriert (`camera_*`, `services_*`) inkl. JSON-Schemas
- [x] `hermes cameras …`-CLI registriert (list/show/stream-url/snapshot-url/snapshot/signaling-login/receiver/services)
- [x] `hermes plugins validate` läuft grün (nur Warnungen: sudo-Nutzung, Binärdatei)
- [x] Plugin lädt im echten Hermes-Loader: `enabled=true`, 13 Tools, keine Fehler
- [x] Samba/MiniDLNA-Steuerung (`services.py`) ohne Fremdabhängigkeit eingebunden
- [x] `plugin.json` (Agent Plugins v1) an Version/Kommandos angeglichen
- [x] Dashboard-Tab + Desktop-Seite (`dashboard/`, `desktop/`) ins Repo übernommen
- [x] Installation dokumentiert (`hermes plugins install <pfad>` bzw. `~/.hermes/plugins/`)
- [x] **Einrichten im Hermes-Dashboard:** Dashboard-Tab mit Kamera-Formular (anlegen/ändern/löschen/testen)
- [x] **Dienste einrichten:** Samba/MiniDLNA im Tab starten/stoppen + Autostart (systemctl enable/disable)
- [x] Konfigurations-Store (`config_store.py`): CRUD, Validierung, atomares Schreiben + `.bak`, gemeinsames Basis-Home
- [x] Neue Agent-Tools `camera_add/update/remove/test` + `services_enable/disable` (19 Tools)
- [x] CLI erweitert: `hermes cameras add|update|remove|test|services-enable|services-disable`
- [x] **Lokaler Relay-Server** (`relay.py`): Signalisierung + STUN + RTP/JPEG + HTTP-Vorschau
      (`/status`, `/snapshot.jpg`, `/stream.mjpg`), als systemd-User-Dienst installierbar
- [x] Dashboard-Sektion „Lokaler Relay-Server“ (Installieren/Starten/Stoppen/Deinstallieren + Live-Vorschau)
- [x] Tools/CLI `relay_status|relay_install|relay_start|relay_stop|relay_uninstall`
- [x] **Autoconf:** Kameras automatisch finden (WLAN-AP-Scan `ZIOTA_*`, BLE-Advertising,
      aktiver Kamera-AP inkl. RTSP-8266-Query) und als Geräte anlegen
- [x] Dashboard-Button „Autoconf" + Tool `camera_autoconf` + `hermes cameras autoconf [--apply]`
- [x] **WLAN-Provisionierung über Kamera-AP** (TCP 8266): Dashboard-Karte „Kamera ins WLAN bringen",
      Tool `camera_provision_wifi`, CLI `hermes cameras provision`, `hermes cameras wifi`
- [x] Live verifiziert: Kamera `ZIOTA_196758286858` joint Heim-WLAN und streamt RTP/JPEG an den
      lokalen Relay (Frames, 640×480, Audio)
- [x] **Mehrkamera:** pro Login eigener UDP-Media-Port (`MediaHub`), `/cameras`, per-UID-Snapshots/Streams
- [x] **Qualitätsstufen** (`original`/`high`/`medium`/`low`) + FPS für Vorschau/Snapshots (Pillow),
      im Dashboard und über Plugin-Einstellungen/CLI wählbar
- [x] Harte Container-Pfade (`/workspace/iwfcam`, `/home/fm/smbdlna`) entfernt
- [x] `setup.py` auf 0.3.0 + Package-Data aktualisiert; `websocket-client` optional beim Import
- [ ] Veröffentlichung: GitHub-Repo `sademardotDE/iwfcam4hermes` steht noch auf 0.2.0 — 0.3.0 dort einspielen/pushen

## Phase 4: iWFCam P2P-Adapter
- [ ] JNI-Funktionen über ctypes/NDK-JNI aufrufen (Cross-Compilation oder Emulation)
- [ ] `AddNewP2PDevice`, `UpdateP2PDevice`, `DeleteP2PDevice` implementieren
- [ ] `reqDevIPInfor`, `setP2PDevIPInfor`, `readP2PDevIPInfor` implementieren
- [ ] `reqP2PDeviceAVMedia`, `stopP2PDeviceAVMedia` implementieren
- [ ] `sendP2PDeviceTalkAudioData`, `keepP2PDeviceWakeup` implementieren
- [ ] P2P-Magic-Header `P2P\x00` Protokoll implementieren
- [ ] Relay-Modus und AP-Modus unterstützen

## Phase 5: Snapshot & Stream
- [ ] Snapshot-Abruf für beide Typen validieren (HTTP + P2P)
- [ ] Live-Stream-Weiterleitung an Dashboards (RTSP/HTTP)
- [x] Live-Stream-Verteilung vorbereitet (`stream_proxy.py`)
- [x] Hermes-UI-Integration (`hermes_plugin.py`, `plugin_tools.py`, Dashboard/Desktop)

## Phase 6: Tests & Dokumentation
- [x] Unit-Tests für Adapter, RTP, Receiver, BLE und Plugin-Vertrag (57 Tests, grün)
- [x] Integrationstests mit simulierter Kamera / Mock-Snapshots
- [x] Dokumentation (README, `docs/PROTOCOL.md`, `docs/BLE_PROVISIONING.md`)
- [ ] Performance-Tests mit echter Kamera

## Blocker
- `libZGP2PComm.so` ist ARM (aarch64), Host ist x86_64 → Cross-Compilation oder QEMU-Emulation nötig
- Keine echten Kameras für Live-Tests verfügbar
- Kamera-GUI braucht opencv-python, pillow und Tk-Laufzeit (auf diesem Host fehlen cv2/libtk8.6)
- GitHub-Repo ist gegenüber dem lokalen Arbeitsstand veraltet (0.2.0 vs. 0.3.0)
