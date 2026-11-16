# Dokumentation — iwfcam4hermes

Index der Unterlagen zu diesem Plugin (Version **0.12.1**, Stand 16.11.2026).

| Dokument | Inhalt |
| --- | --- |
| [../README.md](../README.md) | Einstieg: Installation, Tools/CLI, Dashboard & Desktop, Provisionierung, Relay, Konfiguration, Tests, Änderungsprotokoll |
| [PROTOCOL.md](PROTOCOL.md) | Z-IOT-Protokoll: Signalisierung, Login/Reply, RTP/JPEG, AP-Modus-RTSP, **AP-Provisionierung (TCP 8266)**, STUN, BLE |
| [BLE_PROVISIONING.md](BLE_PROVISIONING.md) | BLE-Provisionierung: Voraussetzungen, Ablauf, Troubleshooting, verifizierter Stand (`TXW817_D`-GATT) |
| [screenshots/README.md](screenshots/README.md) | Verifizierte UI-Stände (Dashboard/Desktop): Mehrkamera, Zustände, Reconnect, Snapshots |
| [../TASKS.md](../TASKS.md) | Aufgaben-/Statusübersicht: erledigt, offen, Umgebung |
| [../README.md#quellen--danksagung](../README.md#quellen--danksagung) | **Quellen & Danksagung**: eigenes Reverse-Engineering (`china-spy-cam`), `open-ziot`, `cam-reverse` |

## Kurzüberblick

- **Agent-Tools:** 24 (`camera_*`, `relay_*`) · CLI: `hermes cameras …`
- **Oberflächen:** Dashboard-Tab `/iwfcam`, Hermes-Desktop-Seite `/iwfcam`,
  Watchdog-Status in der Relay-Karte
- **Relay:** Signaling 8882 (TCP), STUN 13478 (UDP), Medien pro Kamera (UDP),
  HTTP-Vorschau 8099 (`/status`, `/cameras`, `/snapshot.jpg`, `/stream.mjpg`,
  `/snapshots`, `/watchdog`)
- **Tests:** 127 Kern-Tests + 21 Dashboard-API-Tests, Validator OK

## Tests ausführen

```bash
# Kern-Suite
python3 -m pytest iwfcam4hermes -q -p no:syrupy

# Dashboard-API (braucht fastapi/httpx; eigenes Test-Venv)
python3 -m venv .venv-dashboard-test
.venv-dashboard-test/bin/pip install pytest fastapi httpx requests
.venv-dashboard-test/bin/python -m pytest iwfcam4hermes/test_dashboard_api.py -q
```
