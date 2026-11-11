// iwfcam4hermes — Desktop half. A full page (route + sidebar row + palette command)
// for the WiFi cameras: camera CRUD/autoconf, multi-camera relay previews with
// quality, WLAN provisioning (SSID + password) and Samba/MiniDLNA service control.
// Everything goes through this package's dashboard backend via ctx.rest
// (namespace: /api/plugins/iwfcam4hermes).
import { host, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PATH = '/iwfcam'
const ID = 'iwfcam4hermes'
const QUALITIES = ['original', 'high', 'medium', 'low']
const SERVICE_LABELS = { smb: 'Samba (smb + nmb)', dlna: 'MiniDLNA' }

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '6px 8px',
  borderRadius: '6px',
  border: '1px solid var(--ui-stroke-secondary, rgba(128,128,128,.35))',
  background: 'var(--ui-surface, transparent)',
  color: 'var(--ui-text-primary, inherit)',
  fontSize: '13px'
}
const labelStyle = {
  display: 'block',
  fontSize: '11px',
  color: 'var(--ui-text-secondary, #888)',
  marginBottom: '2px'
}
const muted = { fontSize: '12px', color: 'var(--ui-text-secondary, #888)' }
const cardStyle = {
  border: '1px solid var(--ui-stroke-secondary, rgba(128,128,128,.25))',
  borderRadius: '8px',
  padding: '12px',
  marginBottom: '12px'
}
const buttonStyle = {
  padding: '4px 10px',
  fontSize: '12px',
  borderRadius: '6px',
  border: '1px solid var(--ui-stroke-secondary, rgba(128,128,128,.35))',
  background: 'transparent',
  color: 'var(--ui-text-primary, inherit)',
  cursor: 'pointer'
}

function Btn(props) {
  return jsx('button', {
    onClick: props.onClick,
    disabled: !!props.disabled,
    style: Object.assign({}, buttonStyle, props.style || {}),
    children: props.children
  })
}

function Field({ label, children }) {
  return jsxs('div', {
    style: { marginBottom: '8px' },
    children: [jsx('label', { style: labelStyle, children: label }), children]
  })
}

function errText(err) {
  return err && err.message ? err.message : String(err)
}

function emptyDevice() {
  return {
    id: '', name: '', type: 'iwfcam', uid: '', host: '', port: '', username: '',
    password: '', channel: 0, stream_path: '/live', snapshot_path: '/snapshot',
    relay_mode: false, mock: false, notes: ''
  }
}

function DeviceForm({ rest, initial, onSaved, onCancel }) {
  const editing = !!initial && !!initial.id
  const [form, setForm] = useState(initial || emptyDevice())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const set = (key, value) => setForm((prev) => Object.assign({}, prev, { [key]: value }))
  const text = (key) => (ev) => set(key, ev.target.value)
  const num = (key) => (ev) => set(key, ev.target.value === '' ? '' : Number(ev.target.value))
  const check = (key) => (ev) => set(key, !!ev.target.checked)

  function save() {
    const device = {
      id: String(form.id || '').trim(),
      name: String(form.name || '').trim(),
      type: form.type || 'iwfcam',
      uid: String(form.uid || '').trim() || null,
      host: String(form.host || '').trim() || null,
      port: form.port === '' || form.port === null ? null : Number(form.port),
      username: String(form.username || '').trim() || null,
      password: form.password ? String(form.password) : null,
      channel: form.channel === '' ? 0 : Number(form.channel),
      stream_path: String(form.stream_path || '/live'),
      snapshot_path: String(form.snapshot_path || '/snapshot'),
      relay_mode: !!form.relay_mode,
      mock: !!form.mock,
      notes: String(form.notes || '')
    }
    setSaving(true)
    setError(null)
    const request = editing
      ? rest('/devices/' + encodeURIComponent(device.id), { method: 'PUT', body: device })
      : rest('/devices', { method: 'POST', body: device })
    request
      .then(() => onSaved && onSaved())
      .catch((err) => setError(errText(err)))
      .then(() => setSaving(false))
  }

  return jsxs('div', { style: cardStyle, children: [
    jsxs('div', {
      style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' },
      children: [
        jsx('strong', { children: editing ? 'Kamera bearbeiten' : 'Neue Kamera' }),
        jsx('span', { style: muted, children: editing ? 'ID bleibt unverändert' : 'Pflicht: id + name' })
      ]
    }),
    jsx('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '8px' }, children: [
      jsx(Field, { label: 'ID', children: jsx('input', { style: inputStyle, value: form.id, disabled: editing, onChange: text('id') }) }),
      jsx(Field, { label: 'Name', children: jsx('input', { style: inputStyle, value: form.name, onChange: text('name') }) }),
      jsx(Field, { label: 'Typ', children: jsx('select', { style: inputStyle, value: form.type, onChange: text('type') }, ['iwfcam', 'ziota', 'pppp'].map((t) => jsx('option', { value: t, children: t }, t))) }),
      jsx(Field, { label: 'UID', children: jsx('input', { style: inputStyle, value: form.uid || '', onChange: text('uid') }) }),
      jsx(Field, { label: 'Host', children: jsx('input', { style: inputStyle, value: form.host || '', onChange: text('host') }) }),
      jsx(Field, { label: 'Port', children: jsx('input', { style: inputStyle, type: 'number', value: form.port === null ? '' : form.port, onChange: num('port') }) }),
      jsx(Field, { label: 'Benutzer', children: jsx('input', { style: inputStyle, value: form.username || '', onChange: text('username') }) }),
      jsx(Field, { label: 'Passwort', children: jsx('input', { style: inputStyle, type: 'password', value: form.password || '', onChange: text('password') }) }),
      jsx(Field, { label: 'Kanal', children: jsx('input', { style: inputStyle, type: 'number', value: form.channel, onChange: num('channel') }) }),
      jsx(Field, { label: 'Stream-Pfad', children: jsx('input', { style: inputStyle, value: form.stream_path || '', onChange: text('stream_path') }) }),
      jsx(Field, { label: 'Snapshot-Pfad', children: jsx('input', { style: inputStyle, value: form.snapshot_path || '', onChange: text('snapshot_path') }) }),
      jsx(Field, { label: 'Notizen', children: jsx('input', { style: inputStyle, value: form.notes || '', onChange: text('notes') }) })
    ] }),
    jsxs('div', { style: { display: 'flex', gap: '16px', margin: '4px 0 10px' }, children: [
      jsx('label', { style: { fontSize: '13px', display: 'flex', gap: '6px', alignItems: 'center' }, children: [
        jsx('input', { type: 'checkbox', checked: !!form.relay_mode, onChange: check('relay_mode') }), 'Relay-Modus (RTSP)'
      ] }),
      jsx('label', { style: { fontSize: '13px', display: 'flex', gap: '6px', alignItems: 'center' }, children: [
        jsx('input', { type: 'checkbox', checked: !!form.mock, onChange: check('mock') }), 'Mock-Kamera'
      ] })
    ] }),
    error ? jsx('div', { style: { color: 'var(--ui-danger, #d33)', fontSize: '12px', marginBottom: '6px' }, children: error }) : null,
    jsxs('div', { style: { display: 'flex', gap: '8px' }, children: [
      jsx(Btn, { onClick: save, disabled: saving, children: saving ? 'Speichern …' : 'Speichern' }),
      jsx(Btn, { onClick: onCancel, disabled: saving, children: 'Abbrechen' })
    ] })
  ] })
}

function DeviceRow({ device, image, onSnap, onEdit, onDelete, onTest, test, busy }) {
  const detail = [device.host, device.port ? ':' + device.port : '', device.stream_url || '']
    .filter(Boolean).join(' · ') || 'kein Endpunkt'
  return jsxs('div', { style: cardStyle, children: [
    jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }, children: [
      jsx('strong', { children: device.name }),
      jsx('span', { style: muted, children: device.type }),
      device.mock ? jsx('span', { style: muted, children: 'mock' }) : null,
      device.uid ? jsx('span', { style: muted, children: device.uid }) : null
    ] }),
    jsx('div', { style: { color: 'var(--ui-text-secondary, #888)', fontSize: '12px', marginTop: '4px' }, children: detail }),
    test ? jsx('div', {
      style: { fontSize: '12px', marginTop: '4px', color: test.reachable ? 'var(--ui-success, #2a7)' : 'var(--ui-danger, #d33)' },
      children: (test.reachable ? '✓ ' : '✗ ') + (test.detail || '')
    }) : null,
    jsxs('div', { style: { marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }, children: [
      jsx(Btn, { onClick: onSnap, disabled: busy, children: 'Snapshot' }),
      jsx(Btn, { onClick: onTest, disabled: busy, children: 'Test' }),
      jsx(Btn, { onClick: onEdit, disabled: busy, children: 'Bearbeiten' }),
      jsx(Btn, { onClick: onDelete, disabled: busy, children: 'Löschen' })
    ] }),
    image ? jsx('img', { src: image, alt: device.name, style: { marginTop: '8px', maxWidth: '100%', borderRadius: '6px', display: 'block' } }) : null
  ] })
}

function CamerasSection({ rest, devices, reload }) {
  const [form, setForm] = useState(null)
  const [images, setImages] = useState({})
  const [tests, setTests] = useState({})
  const [busy, setBusy] = useState({})
  const [autoconf, setAutoconf] = useState(null)
  const [error, setError] = useState(null)

  const setBusyFor = (id, value) => setBusy((prev) => Object.assign({}, prev, { [id]: value }))

  function snap(id) {
    setBusyFor(id, true)
    rest('/snapshot/' + encodeURIComponent(id))
      .then((r) => setImages((prev) => Object.assign({}, prev, { [id]: r.image || null })))
      .catch(() => setImages((prev) => Object.assign({}, prev, { [id]: null })))
      .then(() => setBusyFor(id, false))
  }

  function test(id) {
    setBusyFor(id, true)
    rest('/devices/' + encodeURIComponent(id) + '/test', { method: 'POST', body: {} })
      .then((r) => setTests((prev) => Object.assign({}, prev, { [id]: r })))
      .catch((err) => setTests((prev) => Object.assign({}, prev, { [id]: { reachable: false, detail: errText(err) } })))
      .then(() => setBusyFor(id, false))
  }

  function edit(id) {
    rest('/devices/' + encodeURIComponent(id))
      .then((r) => setForm(r.device))
      .catch((err) => setError(errText(err)))
  }

  function remove(id) {
    setBusyFor(id, true)
    rest('/devices/' + encodeURIComponent(id), { method: 'DELETE' })
      .then(() => reload())
      .catch((err) => setError(errText(err)))
      .then(() => setBusyFor(id, false))
  }

  function runAutoconf() {
    setAutoconf({ loading: true })
    rest('/devices/autoconf', { method: 'POST', body: { apply: false, mode: 'both' } })
      .then((r) => setAutoconf({ loading: false, data: r }))
      .catch((err) => { setAutoconf(null); setError(errText(err)) })
  }

  function applyAutoconf(suggestion) {
    rest('/devices', { method: 'POST', body: suggestion })
      .then(() => {
        reload()
        setAutoconf((prev) => {
          if (!prev || !prev.data) return prev
          const data = Object.assign({}, prev.data)
          data.suggestions = (data.suggestions || []).filter((s) => s.id !== suggestion.id)
          return Object.assign({}, prev, { data })
        })
      })
      .catch((err) => setError(errText(err)))
  }

  function applyAutoconfAll() {
    rest('/devices/autoconf', { method: 'POST', body: { apply: true, mode: 'both' } })
      .then(() => { reload(); setAutoconf(null) })
      .catch((err) => setError(errText(err)))
  }

  return jsxs('div', { children: [
    jsxs('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }, children: [
      jsx('h3', { style: { margin: 0 }, children: 'Kameras (' + devices.length + ')' }),
      jsxs('div', { style: { display: 'flex', gap: '8px' }, children: [
        jsx(Btn, { onClick: runAutoconf, disabled: autoconf && autoconf.loading, children: autoconf && autoconf.loading ? 'Suche …' : 'Autoconf' }),
        jsx(Btn, { onClick: () => setForm(form ? null : emptyDevice()), children: form ? 'Formular schließen' : '+ Neue Kamera' })
      ] })
    ] }),
    autoconf && autoconf.data ? jsxs('div', { style: cardStyle, children: [
      jsxs('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }, children: [
        jsx('strong', { children: 'Autoconf: ' + (autoconf.data.found || 0) + ' Kamera(s) gefunden' }),
        (autoconf.data.suggestions || []).length > 1
          ? jsx(Btn, { onClick: applyAutoconfAll, children: 'Alle hinzufügen' })
          : null
      ] }),
      autoconf.data.ble_error ? jsx('div', { style: muted, children: autoconf.data.ble_error }) : null,
      (autoconf.data.suggestions || []).length
        ? (autoconf.data.suggestions || []).map((s) => jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px', flexWrap: 'wrap' }, children: [
            jsx('strong', { children: s.name }), jsx('span', { style: muted, children: s.uid }),
            jsx('span', { style: muted, children: (s.host || '') + (s.port ? ':' + s.port : '') }),
            jsx(Btn, { onClick: () => applyAutoconf(s), children: 'Hinzufügen' })
          ] }, s.id))
        : jsx('div', { style: Object.assign({}, muted, { marginTop: '6px' }), children: 'Keine neuen ZIOT-Kameras gefunden.' }),
      jsx('div', { style: { marginTop: '8px' }, children: jsx(Btn, { onClick: () => setAutoconf(null), children: 'Schließen' }) })
    ] }) : null,
    error ? jsx('div', { style: { color: 'var(--ui-danger, #d33)', fontSize: '12px', marginBottom: '8px' }, children: 'Fehler: ' + error }) : null,
    form ? jsx(DeviceForm, {
      rest,
      initial: form,
      onSaved: () => { setForm(null); reload() },
      onCancel: () => setForm(null)
    }) : null,
    devices.map((d) => jsx(DeviceRow, {
      key: d.id,
      device: d,
      image: images[d.id],
      test: tests[d.id],
      busy: !!busy[d.id],
      onSnap: () => snap(d.id),
      onTest: () => test(d.id),
      onEdit: () => edit(d.id),
      onDelete: () => remove(d.id)
    }))
  ] })
}

function RelaySection({ rest, devices }) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [publicIp, setPublicIp] = useState('')
  const [quality, setQuality] = useState('medium')
  const [fps, setFps] = useState(5)
  const [images, setImages] = useState({})
  const [busy, setBusy] = useState({})

  function load() {
    rest('/relay')
      .then((r) => {
        setStatus(r)
        const cfg = r.configured || {}
        if (cfg.public_ip) setPublicIp((prev) => prev || cfg.public_ip)
        if (cfg.quality) setQuality(cfg.quality)
        if (cfg.fps) setFps(cfg.fps)
      })
      .catch((err) => setError(errText(err)))
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const cameras = (status && status.cameras) || []
  const cameraKey = cameras.map((c) => c.uid + ':' + c.frames).join(',')

  useEffect(() => {
    if (!cameras.length) return
    let alive = true
    function grab() {
      cameras.forEach((c) => {
        rest('/relay/snapshot?uid=' + encodeURIComponent(c.uid) + '&quality=' + encodeURIComponent(quality))
          .then((r) => { if (alive) setImages((prev) => Object.assign({}, prev, { [c.uid]: r.image || null })) })
          .catch(() => { /* noch kein Frame */ })
      })
    }
    grab()
    const timer = setInterval(grab, Math.max(1000, 1000 / Math.max(1, Number(fps) || 5)))
    return () => { alive = false; clearInterval(timer) }
  }, [cameraKey, quality, fps])

  function act(action) {
    setBusy((prev) => Object.assign({}, prev, { [action]: true }))
    setError(null)
    rest('/relay/' + action, { method: 'POST', body: { public_ip: publicIp, quality, fps } })
      .then(() => load())
      .catch((err) => setError(errText(err)))
      .then(() => setBusy((prev) => { const next = Object.assign({}, prev); delete next[action]; return next }))
  }

  function nameFor(uid) {
    const normalized = String(uid || '').toUpperCase().replace(/^ZIOTA_/, '')
    for (const device of devices) {
      const deviceUid = String(device.uid || '').toUpperCase().replace(/^ZIOTA_/, '')
      if (deviceUid && deviceUid === normalized) return device.name
    }
    return 'ZIOTA ' + normalized
  }

  if (error && !status) return jsx('div', { style: { color: 'var(--ui-danger, #d33)' }, children: 'Relay: ' + error })
  if (!status) return jsx('div', { style: muted, children: 'Lade Relay …' })

  const cfg = status.configured || {}
  const totals = (status.stats && status.stats.totals) || {}

  return jsxs('div', { style: cardStyle, children: [
    jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '6px' }, children: [
      jsx('strong', { children: 'Lokaler Relay-Server (Mehrkamera)' }),
      jsx('span', { style: muted, children: status.installed ? 'installiert' : 'nicht installiert' }),
      jsx('span', { style: muted, children: status.active ? 'läuft' : 'gestoppt' }),
      jsx('span', { style: muted, children: (totals.cameras || 0) + ' Kamera(s), ' + (totals.frames || 0) + ' Frames' })
    ] }),
    jsx('div', { style: muted, children: 'Signalisierung ' + (cfg.signaling_port || '–') + ' · STUN ' + (cfg.stun_port || '–') + ' · HTTP ' + (cfg.http_port || '–') }),
    jsxs('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', marginTop: '8px' }, children: [
      jsx('input', { style: Object.assign({}, inputStyle, { maxWidth: '180px' }), value: publicIp, onChange: (ev) => setPublicIp(ev.target.value), placeholder: 'LAN-IPv4' }),
      jsx('select', { style: Object.assign({}, inputStyle, { maxWidth: '140px' }), value: quality, onChange: (ev) => setQuality(ev.target.value) },
        QUALITIES.map((q) => jsx('option', { value: q, children: 'Qualität: ' + q }, q))),
      jsx('label', { style: { fontSize: '12px', display: 'flex', gap: '4px', alignItems: 'center' }, children: [
        'FPS', jsx('input', { style: Object.assign({}, inputStyle, { width: '60px' }), type: 'number', min: 1, max: 30, value: fps, onChange: (ev) => setFps(Number(ev.target.value) || 1) })
      ] }),
      jsx(Btn, { onClick: () => act('install'), disabled: busy.install, children: status.installed ? 'Unit aktualisieren' : 'Als Dienst installieren' }),
      status.active
        ? jsx(Btn, { onClick: () => act('stop'), disabled: busy.stop, children: 'Stoppen' })
        : jsx(Btn, { onClick: () => act('start'), disabled: busy.start || !status.installed, children: 'Starten' }),
      jsx(Btn, { onClick: () => act('uninstall'), disabled: busy.uninstall || !status.installed, children: 'Deinstallieren' })
    ] }),
    error ? jsx('div', { style: { color: 'var(--ui-danger, #d33)', fontSize: '12px', marginTop: '6px' }, children: error }) : null,
    jsx('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px', marginTop: '10px' }, children:
      cameras.length
        ? cameras.map((c) => jsxs('div', { style: cardStyle, children: [
            jsxs('div', { style: { display: 'flex', justifyContent: 'space-between', gap: '6px' }, children: [
              jsx('strong', { style: { fontSize: '13px' }, children: nameFor(c.uid) }),
              jsx('span', { style: muted, children: 'UDP ' + (c.port || '–') })
            ] }),
            jsx('div', { style: muted, children: 'Frames ' + (c.frames || 0) + (c.width ? ' · ' + c.width + '×' + c.height : '') + ' · Audio ' + (c.audio_packets || 0) }),
            images[c.uid]
              ? jsx('img', { src: images[c.uid], alt: nameFor(c.uid), style: { marginTop: '6px', width: '100%', borderRadius: '6px', display: 'block' } })
              : jsx('div', { style: Object.assign({}, muted, { marginTop: '6px' }), children: 'Warte auf Frame …' })
          ] }, c.uid))
        : jsx('div', { style: muted, children: status.active ? 'Noch keine Kamera verbunden — Kamera provisionieren (unten).' : 'Relay gestoppt.' })
    })
  ] })
}

function ProvisionSection({ rest, onProvisioned }) {
  const [wifi, setWifi] = useState(null)
  const [form, setForm] = useState({ camera_ssid: '', ssid: '', password: '', server_ip: '', server_port: 8882, utc_offset: 60, auto_connect: true })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  function load() {
    rest('/wifi')
      .then((r) => {
        setWifi(r)
        const cams = r.camera_aps || []
        const nets = r.networks || []
        let preferred = null
        for (const n of nets) { if (!n.is_camera_ap && n.band === '2.4 GHz' && n.security) { preferred = n; break } }
        setForm((prev) => Object.assign({}, prev, {
          camera_ssid: prev.camera_ssid || (cams.length ? cams[0].ssid : ''),
          ssid: prev.ssid || (preferred ? preferred.ssid : ''),
          server_ip: prev.server_ip || ((r.current && r.current.ipv4) || '')
        }))
      })
      .catch((err) => setError(errText(err)))
  }
  useEffect(() => { load() }, [])

  const set = (key) => (ev) => setForm((prev) => Object.assign({}, prev, { [key]: ev.target.value }))
  const setNum = (key) => (ev) => setForm((prev) => Object.assign({}, prev, { [key]: Number(ev.target.value) || 0 }))

  function run() {
    setBusy(true); setError(null); setResult(null)
    rest('/provision', { method: 'POST', body: form })
      .then((r) => { setResult(r); if (onProvisioned) onProvisioned() })
      .catch((err) => setError(errText(err)))
      .then(() => setBusy(false))
  }

  const cams = (wifi && wifi.camera_aps) || []
  const nets = ((wifi && wifi.networks) || []).filter((n) => !n.is_camera_ap)
  const current = (wifi && wifi.current) || {}

  return jsxs('div', { style: cardStyle, children: [
    jsxs('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }, children: [
      jsx('strong', { children: 'Kamera ins WLAN bringen' }),
      jsx(Btn, { onClick: load, disabled: busy, children: 'Aktualisieren' })
    ] }),
    jsx('div', { style: Object.assign({}, muted, { marginTop: '4px' }), children:
      'Host-WLAN: ' + (current.ssid || 'nicht verbunden') + (current.ipv4 ? ' (' + current.ipv4 + ')' : '') + ' · Kamera-APs: ' + cams.length }),
    jsxs('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '8px', marginTop: '8px' }, children: [
      jsx(Field, { label: 'Kamera-AP (ZIOTA_…)', children: jsxs('select', { style: inputStyle, value: form.camera_ssid, onChange: set('camera_ssid'), children:
        cams.length ? cams.map((c) => jsx('option', { value: c.ssid, children: c.ssid + ' (' + c.signal + '%)' }, c.ssid)) : jsx('option', { value: '', children: 'kein Kamera-AP gefunden' })
      }) }),
      jsx(Field, { label: 'Ziel-WLAN (2,4 GHz)', children: jsxs('select', { style: inputStyle, value: form.ssid, onChange: set('ssid'), children:
        nets.length ? nets.map((n, i) => jsx('option', { value: n.ssid, children: n.ssid + ' · ' + n.band + ' · ' + (n.security || 'offen') }, n.ssid + i)) : jsx('option', { value: '', children: 'kein WLAN gefunden' })
      }) }),
      jsx(Field, { label: 'WLAN-Passwort', children: jsx('input', { style: inputStyle, type: 'password', value: form.password, onChange: set('password') }) }),
      jsx(Field, { label: 'Relay-Host (LAN-IPv4)', children: jsx('input', { style: inputStyle, value: form.server_ip, onChange: set('server_ip') }) }),
      jsx(Field, { label: 'Relay-Port', children: jsx('input', { style: inputStyle, type: 'number', value: form.server_port, onChange: setNum('server_port') }) }),
      jsx(Field, { label: 'UTC-Offset (Min.)', children: jsx('input', { style: inputStyle, type: 'number', value: form.utc_offset, onChange: setNum('utc_offset') }) })
    ] }),
    jsx('label', { style: { display: 'flex', gap: '6px', alignItems: 'center', fontSize: '13px', margin: '4px 0 8px' }, children: [
      jsx('input', { type: 'checkbox', checked: !!form.auto_connect, onChange: (ev) => setForm((prev) => Object.assign({}, prev, { auto_connect: !!ev.target.checked })) }),
      'Host automatisch mit dem Kamera-AP verbinden (WLAN wird kurz getrennt)'
    ] }),
    jsx(Btn, { onClick: run, disabled: busy || !cams.length, children: busy ? 'Provisioniere …' : 'Kamera ins WLAN bringen' }),
    error ? jsx('div', { style: { color: 'var(--ui-danger, #d33)', fontSize: '12px', marginTop: '8px' }, children: error }) : null,
    result ? jsx('div', { style: { color: 'var(--ui-success, #2a7)', fontSize: '12px', marginTop: '8px' }, children:
      '✓ Kamera ' + (result.camera_uid || '') + ' übernommen: ' + (result.ssid || '') + ' → Relay ' + (result.server || '') }) : null
  ] })
}

function CamerasPage({ rest }) {
  const [devices, setDevices] = useState(null)
  const [error, setError] = useState(null)

  function reload() {
    return rest('/devices')
      .then((r) => setDevices(Array.isArray(r.devices) ? r.devices : []))
      .catch((err) => setError(errText(err)))
  }
  useEffect(() => { reload() }, [])

  if (error && !devices) return jsx('div', { style: { padding: '16px', color: 'var(--ui-danger, #d33)' }, children: 'Fehler: ' + error })
  if (!devices) return jsx('div', { style: { padding: '16px' }, children: 'Lade Kameras …' })

  return jsxs('div', { style: { padding: '16px', maxWidth: '900px' }, children: [
    jsx('h2', { style: { marginTop: 0 }, children: 'Kameras' }),
    jsx(CamerasSection, { rest, devices, reload }),
    jsx(RelaySection, { rest, devices }),
    jsx(ProvisionSection, { rest, onProvisioned: reload }),
  ] })
}

export default {
  id: ID,
  name: 'Kameras',
  register(ctx) {
    const rest = (path, opts) => ctx.rest(path, opts)

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        title: 'Kameras',
        data: { path: PATH },
        render: () => jsx(CamerasPage, { rest })
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: PATH, label: 'Kameras', codicon: 'deviceCameraVideo' }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'iwfcam4hermes.open',
          label: 'Kameras öffnen',
          keywords: ['camera', 'kamera', 'cam', 'iwfcam', 'stream', 'snapshot', 'relay', 'wlan', 'überwachung'],
          run: () => host.navigate(PATH)
        }
      }
    ])
  }
}
