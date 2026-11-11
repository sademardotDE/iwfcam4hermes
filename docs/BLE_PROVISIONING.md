# BLE-Provisioning einer ZIOTA-Kamera unter Linux

Die Kamera (`ZIOTA_<device ID>`) wird per Bluetooth LE mit WLAN-Zugang und
**deinem** Empfänger-Endpunkt versorgt. Danach verbindet sie sich selbstständig
mit deinem Server (statt der Hersteller-Cloud) und streamt RTP/JPEG.

> **Wichtig:** Der BLE-Schritt läuft **nicht** im Hermes-Docker-Container (dort
> fehlen `bluetoothd`, D-Bus und das `AF_BLUETOOTH`-Kernel-Feature). Führe ihn
> auf dem **Linux-Host mit echtem Bluetooth-Adapter** aus.

## Voraussetzungen (Host)

- Bluetooth-Adapter (`hci0`) + BlueZ + D-Bus:
  ```bash
  sudo apt install bluez bluez-tools python3-pip
  sudo systemctl enable --now bluetooth
  rfkill unblock bluetooth
  ```
- Python-Paket bleak (auf dem Host, ggf. in venv):
  ```bash
  pip install bleak            # oder: sudo apt install python3-bleak
  ```
- Bluetooth-Adapter sichtbar/aktiv:
  ```bash
  bluetoothctl show            # "Powered: yes"
  bluetoothctl scan on         # sollte "ZIOTA_..." zeigen
  ```

## Ablauf (auf dem Host)

### 1. Empfänger starten (dieser Rechner nimmt die Kamera auf)

```bash
cd iwfcam4hermes
python3 plugin.py receiver \
    --public-ip 192.168.0.10 \        # LAN-IPv4 dieses Hosts
    --signaling-port 8882 \
    --media-port 10000 \
    --stun-port 13478 \
    --snapshots ./snapshots \
    --dht ref.jpg                     # optional; Default = gebündelte Standard-Huffman-Tabellen (jpeg-huffman.bin)
```

Der Prozess gibt Ports aus und loggt `camera login`. **Lass ihn laufen.**

### 2. Kamera provisionieren (BLE)

```bash
python3 provision_ble.py \
    --name ZIOTA_196758286858 \
    --ssid "MeinWLAN" \
    --password "WLAN-Passwort" \
    --server-ip 192.168.0.10 \
    --server-port 8882 \
    --utc-offset 60
```

Das Tool sucht `ZIOTA_*`, verbindet, schreibt das Provisioning-Paket in
20-Byte-Chunks (150 ms Abstand) und beendet sich. Alternativ direkt adressieren:

```bash
python3 provision_ble.py ... --address AA:BB:CC:DD:EE:FF
```

### 3. Verifizieren

- Im Empfänger-Log erscheint `camera login: uid=ZIOTA_... firmware=...`
- Nach wenigen Sekunden: `stats: {... "frames": N ...}`
- Snapshots landen in `./snapshots/` (bzw. `latest_jpeg`)

## Wichtige Hinweise

- **Nur 2,4-GHz-WLAN** verwenden — die Kamera kann kein 5 GHz.
- WPA2/PSK, kein Enterprise/WPA3-only.
- `--server-ip` **muss** die Adresse sein, die die Kamera im WLAN erreicht
  (LAN-IPv4 des Hosts, nicht `127.0.0.1`).
- UTC-Offset: Deutschland MEZ `60`, MESZ `120` Minuten.
- Das Provisioning-Paket = `86 86 | u16(len+5) | u16(seq) | u16(len) | body | XOR | 0D`;
  Body: `u16(1) | ssid | pw | "host:port" | u16(offset) | u32(reg)`.

## Troubleshooting

| Symptom | Lösung |
|---|---|
| `no ZIOTA_* device found` | Kamera an/nahe, `rfkill unblock bluetooth`, Scan verlängern (`--scan-timeout 20`) |
| `connection failed` | Adapter belegt/aus: `bluetoothctl power on`; alte Pairings entfernen |
| Kein `camera login` im Empfänger | falsche `--server-ip`/Port, 5-GHz-WLAN, Firewall blockt 8882/10000/13478 |
| Bild bleibt schwarz | `--dht ref.jpg` fehlt (Huffman-Tabellen) oder Kamera noch nicht im RTP-Modus |
| `bleak` ImportError | auf dem **Host** `pip install bleak` (nicht im Container) |

## Sicherheit

- WLAN-Zugangsdaten werden nur über BLE an die Kamera übertragen und hier nicht
  gespeichert. Übertrage sie nicht in öffentlichen Notizen/Logs.
- Das Kamera-Protokoll hat auf der Signalisierung **keine starke
  Geräteauthentifizierung** (nur UID-/XOR-Filter). Betreibe den Empfänger nur im
  vertrauenswürdigen Netz.
