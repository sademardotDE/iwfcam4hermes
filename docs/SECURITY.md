# Sicherheit & Datenschutz — iwfcam4hermes

Version 0.17.0 · Stand 16.11.2026

Dieses Plugin ist für den Betrieb im **eigenen LAN** gedacht. Es gibt keine
Cloud-Anbindung für den Betrieb; Kameras sprechen den lokalen Relay an.

## Netzwerk

- **HTTP-Vorschau/API** (`8099`) bindet standardmäßig nur an `127.0.0.1`.
  Nicht ohne Reverse-Proxy/Auth ins Internet exposen.
- **Signalisierung** (TCP 8882) und **STUN** (UDP 13478) müssen für Kameras
  erreichbar sein; sie haben **keine starke Authentifizierung** (UID/XOR-Filter).
  Nur im vertrauenswürdigen Netz betreiben.
- **RTSP im AP-Modus** (`192.168.1.1:7070`) ist offen, solange der Host mit dem
  Kamera-AP verbunden ist.
- Dashboard/Desktop-API ist über die Hermes-Authentifizierung geschützt.

## Geheimnisse

| Geheimnis | Ablage | Hinweis |
| --- | --- | --- |
| Kamera-Benutzer/Passwörter | `config.json` (`0600`) | nur lokal; `.bak` beachten |
| WLAN-SSID/Passwort | `config.json` → `provision` | für Reconnect/Watchdog; Klartext lokal |
| Telegram-Bot-Token / Slack-Webhook | `relay_motion_webhooks` (Plugin-Config) bzw. Relay-Unit | Tokens gewähren Bot-/Kanalzugriff; bei Verdacht rotieren |
| BLE-Pairing | nicht gespeichert | Provisioning überträgt WLAN-Daten an die Kamera |

Empfehlungen:

- `~/.hermes` und `config.json` nur für den eigenen Benutzer lesbar halten.
- Webhook-URLs nicht in Chats/Issues posten (enthalten oft Tokens).
- Bot-Token bei Verdacht über @BotFather neu erzeugen und Eintrag aktualisieren.
- Snapshot-Verzeichnis regelmäßig prüfen/aufräumen (Kamera-Bilder sind sensibel).
- Keine Portfreigaben für 8882/13478/8099 ins Internet.

## Datenhaltung

- Snapshots und Bewegungsbilder liegen unverschlüsselt im Dateisystem
  (`<snapshot_dir>`); Retention: 200/Kamera (Ringpuffer) bzw. 200/Kamera (Motion).
- Motion-Ereignisse sind flüchtig (nur im Relay-Speicher).
- Webhook-Payloads enthalten UID, Score, Zeitstempel und ggf. den Snapshot-Pfad
  (kein Bildinhalt im JSON; Bilder gehen nur bei Telegram als Upload raus).

## Verantwortung

Die Kameras sind Fremd-Hardware mit proprietärem Protokoll; betreibe sie nur in
Netzen, in denen du das Risiko kennst. Dieses Projekt reverse-engineert das
Verhalten zu Interoperabilitätszwecken (siehe Quellen im README).
