# Bewegungsmelder — iwfcam4hermes

Version 0.17.0 · Stand 16.11.2026

Der Relay bekommt jedes Kamerabild. Daraus berechnet `motion.py` einen
Bewegungswert und meldet Ereignisse (UI, Tool/CLI, Webhooks).

## Verfahren

1. JPEG → **Graustufen**, auf **64×48** verkleinert.
2. Vergleich mit dem vorherigen Frame: Ein Pixel gilt als geändert, wenn sich
   der Grauwert um mehr als **12** unterscheidet.
3. `score` = Anteil geänderter Pixel (0…1).
4. Liegt `score` über der Schwelle **und** ist der Cooldown abgelaufen → Ereignis
   `{uid, ts, score, snapshot?}`; optional wird ein JPEG unter
   `<snapshot_dir>/<uid>/motion/<YYYYmmdd-HHMMSS>.jpg` abgelegt (max. 200/Kamera).
5. Ereignisse bleiben im Speicher (Ringpuffer 50/Kamera); nach einem
   Relay-Neustart ist die Liste leer.

Das Verfahren ist eine reine **Bilddifferenz** — schnell, ohne ML, aber ohne
Personenerkennung/Zonen. Lichtwechsel, IR-Umschaltung oder Kamerawackeln können
auslösen; der Cooldown begrenzt Spam.

## Empfindlichkeit

`relay_motion_sensitivity` (1–100) bildet auf die Score-Schwelle ab:

| Sensitivität | Schwelle (score) | entspricht |
| --- | --- | --- |
| 1 | 0.0600 | 6.00 % |
| 10 | 0.0550 | 5.50 % |
| 25 | 0.0467 | 4.67 % |
| 40 | 0.0383 | 3.83 % |
| 50 | 0.0328 | 3.28 % |
| 60 | 0.0272 | 2.72 % |
| 75 | 0.0189 | 1.89 % |
| 90 | 0.0106 | 1.06 % |
| 100 | 0.0050 | 0.50 % |

- **50** ist der Default (~3,3 % geänderte Pixel). Personen/Bewegung im Bild
  liegen meist deutlich darüber.
- Zu viele Fehlalarme (Nacht/IR/Rauschen): Sensitivität **senken** (z. B. 35–45).
- Bewegung wird verpasst: Sensitivität **erhöhen** (60–75).
- `score` und Schwelle stehen live in `GET /motion` bzw. `camera_motion status`.

## Cooldown & Aufbewahrung

- `relay_motion_cooldown` (Default 10 s): pro Kamera höchstens ein Ereignis in
  diesem Zeitraum. Der laufende `score` wird weiter aktualisiert.
- `relay_motion_snapshot` (Default an): Bild zum Ereignis ablegen.
- Bewegungssnapshots liegen getrennt (`<uid>/motion/`) und zählen nicht in den
  Ringpuffer (200/Kamera) hinein.

## Abruf

| Weg | Beispiel |
| --- | --- |
| Tool | `camera_motion action=status` / `events` / `wait` / `test` |
| CLI | `hermes cameras motion status` · `motion events --limit 10` · `motion wait --timeout 120` |
| HTTP | `GET /motion`, `GET /motion/events?limit=…`, `POST /motion/test` |
| UI | Badge je Kamera („Bewegung vor Xs“), Test-Button in der Relay-Karte |

`action=wait` blockiert bis zu `timeout` Sekunden (max. 300) und liefert das
nächste Ereignis — gedacht für Agenten/cron, die auf Bewegung reagieren wollen.

## Webhooks

`relay_motion_webhooks` akzeptiert **mehrere Ziele**, eine Zeile pro Webhook:

```
slack|https://hooks.slack.com/services/…
discord|https://discord.com/api/webhooks/…
ntfy|https://ntfy.sh/mein-topic
telegram|https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>
https://mein-endpoint/hook          # generic (Typ wird erraten)
```

`relay_motion_webhook` bleibt als Einzelziel erhalten (rückwärtskompatibel).

| Typ | Request |
| --- | --- |
| `generic` | JSON: `event`, `uid`, `score`, `ts`, `ts_iso`, `text`, `content`, `snapshot` |
| `slack` | JSON `{"text": message}` |
| `discord` | JSON `{"content": message}` |
| `ntfy` | `text/plain` + Header `Title: Kamera-Bewegung`, `Tags: camera,motion` |
| `telegram` | `sendDocument` (Default) oder `sendPhoto`, `chat_id` + `caption`/`text` |

Jeder Versand läuft asynchron (5 s Timeout); Fehler werden geloggt, nie
propagiert. Bei Telegram: schlägt der Bild-Upload fehl, geht automatisch eine
Textnachricht raus.

### Telegram einrichten

1. Bot bei [@BotFather](https://t.me/BotFather) anlegen → Token.
2. Chat-ID ermitteln: Bot anschreiben, dann
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → `message.chat.id`
   (bei Gruppen: negative ID).
3. Ziel eintragen:

   ```
   telegram|https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>
   ```

4. `hermes cameras relay-install --public-ip <LAN-IP>` → Unit bekommt
   `--motion-webhook …`, Dienst startet neu.
5. Test: `POST /motion/test` oder UI-Button „Test-Benachrichtigung“.

**Qualität:** `relay_motion_photo_mode=document` sendet das Original-JPEG als
Datei (keine Telegram-Komprimierung, beste Qualität); `photo` sendet inline
(komprimiert). `relay_motion_photo=false` schickt nur Text.

## Grenzen

- Nur bei **streamender** Kamera verfügbar (keine Frames = keine Analyse).
- Keine Zonen, keine Objektklassifikation, keine Aufzeichnung.
- Empfindlichkeit hängt von Licht/IR-Nachtmodus und JPEG-Qualität der Kamera ab.
- Ereignisse sind flüchtig (nur Speicher); Snapshots sind persistent.
- Webhooks werden nur bei Ereignissen gesendet (kein Heartbeat).

Weiter: [API.md](API.md) · [CONFIGURATION.md](CONFIGURATION.md) ·
[TROUBLESHOOTING.md](TROUBLESHOOTING.md)
