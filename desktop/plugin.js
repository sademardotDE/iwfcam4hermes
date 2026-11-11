// iwfcam4hermes — Desktop half. A page (route + sidebar row + palette command)
// listing configured WiFi cameras, with inline snapshots served by this package's
// dashboard backend (dashboard/plugin_api.py) under /api/plugins/iwfcam4hermes/.
import { host, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PATH = '/iwfcam'
const ID = 'iwfcam4hermes'

function CameraRow({ device, img, loading, onSnap }) {
  const detail = [device.host, device.port ? `:${device.port}` : '', device.stream_url || '']
    .filter(Boolean)
    .join(' · ') || 'kein Endpunkt'

  return jsxs('div', {
    style: {
      border: '1px solid var(--ui-stroke-secondary, rgba(128,128,128,.25))',
      borderRadius: '8px',
      padding: '12px',
      marginBottom: '12px'
    },
    children: [
      jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }, children: [
        jsx('strong', { children: device.name }),
        jsx('span', { children: device.type, style: { fontSize: '11px', color: 'var(--ui-text-secondary)' } }),
        device.mock ? jsx('span', { children: 'mock', style: { fontSize: '11px', color: 'var(--ui-text-tertiary)' } }) : null
      ] }),
      jsx('div', { children: detail, style: { color: 'var(--ui-text-secondary)', fontSize: '12px', marginTop: '4px' } }),
      jsx('div', { style: { marginTop: '8px' }, children: jsx('button', {
        onClick: onSnap,
        disabled: loading,
        children: loading ? 'Lade …' : 'Snapshot laden',
        style: {
          padding: '4px 10px',
          fontSize: '12px',
          borderRadius: '6px',
          border: '1px solid var(--ui-stroke-secondary)',
          background: 'transparent',
          color: 'var(--ui-text-primary)',
          cursor: 'pointer'
        }
      }) }),
      img ? jsx('img', {
        src: img,
        alt: `${device.name} snapshot`,
        style: { marginTop: '8px', maxWidth: '100%', borderRadius: '6px', display: 'block' }
      }) : null
    ]
  })
}

function CamerasPage({ rest }) {
  const [devices, setDevices] = useState(null)
  const [error, setError] = useState(null)
  const [images, setImages] = useState({})
  const [loading, setLoading] = useState({})

  useEffect(() => {
    let alive = true
    rest('/devices')
      .then((r) => { if (alive) setDevices(Array.isArray(r?.devices) ? r.devices : []) })
      .catch((e) => { if (alive) setError(e?.message || String(e)) })
    return () => { alive = false }
  }, [])

  function snap(id) {
    setLoading((p) => ({ ...p, [id]: true }))
    rest(`/snapshot/${encodeURIComponent(id)}`)
      .then((r) => setImages((p) => ({ ...p, [id]: r?.image || null })))
      .catch(() => setImages((p) => ({ ...p, [id]: null })))
      .then(() => setLoading((p) => ({ ...p, [id]: false })))
  }

  if (error) return jsx('div', { children: `Fehler: ${error}`, style: { padding: '16px', color: 'var(--ui-text-secondary)' } })
  if (!devices) return jsx('div', { children: 'Lade Kameras …', style: { padding: '16px', color: 'var(--ui-text-secondary)' } })
  if (!devices.length) return jsx('div', { children: 'Keine Kameras konfiguriert.', style: { padding: '16px', color: 'var(--ui-text-secondary)' } })

  return jsxs('div', {
    style: { padding: '16px', maxWidth: '720px' },
    children: [
      jsx('h2', { children: `Kameras (${devices.length})` }),
      devices.map((d) => jsx(CameraRow, {
        key: d.id,
        device: d,
        img: images[d.id],
        loading: !!loading[d.id],
        onSnap: () => snap(d.id)
      }))
    ]
  })
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
          keywords: ['camera', 'kamera', 'cam', 'iwfcam', 'stream', 'snapshot', 'überwachung'],
          run: () => host.navigate(PATH)
        }
      }
    ])
  }
}
