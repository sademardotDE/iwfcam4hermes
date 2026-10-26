# iwfcam4hermes

Hermes-Plugin für Wi-Fi-Überwachungskameras (iWFCam/ESNTD & Z-IOT/ZIOTA).

## Struktur

- `plugin.py` — Kernlogik, Datenmodelle, Konfiguration, CLI
- `manager.py` — CameraManager (High-Level-API)
- `hermes_plugin.py` — Hermes-Plugin-Wrapper
- `plugin.json` — Plugin-Manifest
- `ziota_adapter.py` — WebSocket/STUN-Adapter für Z-IOT
- `iwfcam_adapter.py` — ctypes/strings-Adapter für iWFCam
- `iwfcam_p2p.py` — Python-API für iWFCam P2P
- `iwfcam_jni_stubs.py` — 271 JNI-Stubs
- `stun_client.py` — STUN-Client (RFC 5389)
- `stream_proxy.py` — HTTP-Stream-Proxy
- `msg_analyzer.py` — WebSocket-Nachrichtenanalyse
- `config.example.json` — Beispielkonfiguration
- `__init__.py` — Exporte
- `TASKS.md` — Aufgabenliste

## Unterstützte Kameratypen

| Typ | Protokoll | Status |
|-----|-----------|--------|
| iWFCam / ESNTD | proprietäres P2P (libZGP2PComm.so) | Metadaten + Stream-URL |
| Z-IOT / ZIOTA | STUN/WebSocket P2P | Metadaten + Stream-URL |

## Verwendung

```bash
python3 -m iwfcam4hermes.plugin list --config config.json
python3 -m iwfcam4hermes.plugin show --config config.json --device cam1
python3 -m iwfcam4hermes.plugin stream-url --config config.json --device cam1
```

## Nächste Schritte

- P2P-Adapter für beide Kameratypen
- Snapshot-Abruf
- Live-Stream-Verteilung
- Hermes-UI-Integration
