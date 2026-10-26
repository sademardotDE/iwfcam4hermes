# Aufgabenliste – iwfcam4hermes Plugin

## Phase 1: Grundgerüst ✅
- [x] Plugin-Struktur angelegt (`plugin.py`, `__init__.py`, `config.example.json`)
- [x] Camera/CameraType Datenmodelle
- [x] CLI (list, show, stream-url, snapshot-url, snapshot)
- [x] Z-IOT Adapter-Scaffold (`ziota_adapter.py`)
- [x] iWFCam Adapter-Scaffold (`iwfcam_adapter.py`)
- [x] JNI-Stubs generiert (`iwfcam_jni_stubs.py`)
- [x] Snapshot-Abruf via HTTP (`fetch_snapshot`)
- [x] Findings-Dokument (`analysis/findings.md`)

## Phase 2: Z-IOT WebSocket-Adapter
- [x] WebSocket-Verbindung zu `ws.gps555.net:7080/ws` implementieren (Verbindung erfolgreich)
- [ ] Nachrichtenformat analysieren (Server antwortet nicht auf JSON; möglicherweise binäres Protokoll)
- [x] STUN-Client für NAT-Traversierung (`stun.gps555.net:13478`) — implementiert und in ZIOTAdapter integriert
- [ ] Heartbeat-Schleife implementieren
- [ ] Stream-Start/Stop über WebSocket
- [ ] Snapshot-Abruf über WebSocket (falls unterstützt)
- [ ] Fehlerbehandlung und Reconnect-Logik

## Phase 3: iWFCam P2P-Adapter
- [ ] JNI-Funktionen über ctypes/NDK-JNI aufrufen (Cross-Compilation oder Emulation)
- [ ] `AddNewP2PDevice`, `UpdateP2PDevice`, `DeleteP2PDevice` implementieren
- [ ] `reqDevIPInfor`, `setP2PDevIPInfor`, `readP2PDevIPInfor` implementieren
- [ ] `reqP2PDeviceAVMedia`, `stopP2PDeviceAVMedia` implementieren
- [ ] `sendP2PDeviceTalkAudioData`, `keepP2PDeviceWakeup` implementieren
- [ ] P2P-Magic-Header `P2P\x00` Protokoll implementieren
- [ ] Relay-Modus und AP-Modus unterstützen

## Phase 4: Snapshot & Stream
- [ ] Snapshot-Abruf für beide Typen validieren (HTTP + P2P)
- [ ] Live-Stream-Weiterleitung an Dashboards (RTSP/HTTP)
- [x] Live-Stream-Verteilung vorbereitet (`stream_proxy.py`)

- [x] Hermes-UI-Integration vorbereitet (`hermes_plugin.py`)
- [x] Nachrichtenanalyse vorbereitet (`msg_analyzer.py`)

## Phase 6: Tests & Dokumentation
- [ ] Unit-Tests für Adapter und Plugin
- [ ] Integrationstests mit Mock-Kameras
- [ ] Dokumentation (README, API-Referenz)
- [ ] Performance-Tests

## Blocker
- `libZGP2PComm.so` ist ARM (aarch64), Host ist x86_64 → Cross-Compilation oder QEMU-Emulation nötig
- Protokollformat für Z-IOT WebSocket noch nicht vollständig validiert
- Keine echten Kameras für Live-Tests verfügbar
- [x] Plugin-Registrierung vorbereitet (setup.py, plugin.json)
