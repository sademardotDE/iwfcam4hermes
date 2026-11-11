// iwfcam4hermes dashboard tab: Kameras einrichten (anlegen/ändern/löschen/testen,
// Snapshots) und Dienste (Samba/MiniDLNA) starten/stoppen + Autostart schalten.
// Plain IIFE, no build step, no imports — React comes from the host SDK.
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  var React = SDK.React;
  var h = React.createElement;
  var hooks = SDK.hooks || {};
  var components = SDK.components || {};
  var useState = hooks.useState || React.useState;
  var useEffect = hooks.useEffect || React.useEffect;

  var Card = components.Card || function (p) { return h("div", p); };
  var CardHeader = components.CardHeader || function (p) { return h("div", p); };
  var CardTitle = components.CardTitle || function (p) { return h("h3", p); };
  var CardContent = components.CardContent || function (p) { return h("div", p); };
  var Badge = components.Badge || function (p) { return h("span", p); };
  var Button = components.Button || function (p) { return h("button", p); };

  var API_BASE = "/api/plugins/iwfcam4hermes";
  var DEVICE_TYPES = ["iwfcam", "ziota", "pppp"];
  var SERVICE_LABELS = { smb: "Samba (smb + nmb)", dlna: "MiniDLNA" };

  function api(path, options) {
    return SDK.fetchJSON(API_BASE + path, options);
  }
  function apiJSON(method, path, body) {
    return api(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }
  function errText(err) {
    return err && err.message ? err.message : String(err);
  }

  var inputStyle = {
    width: "100%",
    boxSizing: "border-box",
    padding: "6px 8px",
    borderRadius: "6px",
    border: "1px solid var(--ui-stroke-secondary, rgba(128,128,128,.35))",
    background: "var(--ui-surface, transparent)",
    color: "var(--ui-text-primary, inherit)",
    fontSize: "13px"
  };
  var labelStyle = {
    display: "block",
    fontSize: "12px",
    color: "var(--ui-text-secondary, #888)",
    marginBottom: "2px"
  };
  var fieldStyle = { marginBottom: "8px" };

  function Field(props) {
    return h("div", { style: Object.assign({}, fieldStyle, props.wide ? { gridColumn: "1 / -1" } : {}) },
      h("label", { style: labelStyle }, props.label),
      props.children
    );
  }

  function emptyDevice() {
    return {
      id: "", name: "", type: "iwfcam", uid: "", host: "", port: "",
      username: "", password: "", channel: 0, stream_path: "/live",
      snapshot_path: "/snapshot", relay_mode: false, mock: false, notes: ""
    };
  }

  function DeviceForm(props) {
    var editing = !!props.initial && !!props.initial.id;
    var start = useState(props.initial || emptyDevice());
    var form = start[0], setForm = start[1];
    var savingState = useState(false);
    var saving = savingState[0], setSaving = savingState[1];
    var errState = useState(null);
    var error = errState[0], setError = errState[1];

    function set(key, value) {
      setForm(function (prev) { var n = Object.assign({}, prev); n[key] = value; return n; });
    }
    function text(key) {
      return function (ev) { set(key, ev.target.value); };
    }
    function num(key) {
      return function (ev) {
        var v = ev.target.value;
        set(key, v === "" ? "" : Number(v));
      };
    }
    function check(key) {
      return function (ev) { set(key, !!ev.target.checked); };
    }

    function save() {
      var device = {
        id: String(form.id || "").trim(),
        name: String(form.name || "").trim(),
        type: form.type || "iwfcam",
        uid: String(form.uid || "").trim() || null,
        host: String(form.host || "").trim() || null,
        port: form.port === "" || form.port === null ? null : Number(form.port),
        username: String(form.username || "").trim() || null,
        password: form.password ? String(form.password) : null,
        channel: form.channel === "" ? 0 : Number(form.channel),
        stream_path: String(form.stream_path || "/live"),
        snapshot_path: String(form.snapshot_path || "/snapshot"),
        relay_mode: !!form.relay_mode,
        mock: !!form.mock,
        notes: String(form.notes || "")
      };
      setSaving(true);
      setError(null);
      var request = editing
        ? apiJSON("PUT", "/devices/" + encodeURIComponent(device.id), device)
        : apiJSON("POST", "/devices", device);
      request
        .then(function () { if (props.onSaved) props.onSaved(); })
        .catch(function (err) { setError(errText(err)); })
        .then(function () { setSaving(false); });
    }

    return h("div", {
      style: {
        border: "1px solid var(--ui-stroke-secondary, rgba(128,128,128,.25))",
        borderRadius: "8px",
        padding: "12px",
        marginBottom: "12px"
      }
    },
      h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" } },
        h("strong", null, editing ? "Kamera bearbeiten: " + (props.initial.name || props.initial.id) : "Neue Kamera"),
        h("span", { style: { fontSize: "12px", color: "var(--ui-text-secondary, #888)" } },
          editing ? "ID bleibt unverändert" : "Pflicht: id + name")
      ),
      h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "8px" } },
        h(Field, { label: "ID" }, h("input", {
          style: inputStyle, value: form.id, disabled: editing, onChange: text("id"),
          placeholder: "cam1"
        })),
        h(Field, { label: "Name" }, h("input", {
          style: inputStyle, value: form.name, onChange: text("name"), placeholder: "Wohnzimmer"
        })),
        h(Field, { label: "Typ" }, h("select", { style: inputStyle, value: form.type, onChange: text("type") },
          DEVICE_TYPES.map(function (t) { return h("option", { key: t, value: t }, t); }))),
        h(Field, { label: "UID (optional)" }, h("input", {
          style: inputStyle, value: form.uid || "", onChange: text("uid"), placeholder: "ZIOTA_…"
        })),
        h(Field, { label: "Host" }, h("input", {
          style: inputStyle, value: form.host || "", onChange: text("host"), placeholder: "192.168.0.50"
        })),
        h(Field, { label: "Port" }, h("input", {
          style: inputStyle, type: "number", value: form.port === null ? "" : form.port,
          onChange: num("port"), placeholder: "554 / 8080 / 7070"
        })),
        h(Field, { label: "Benutzer" }, h("input", {
          style: inputStyle, value: form.username || "", onChange: text("username")
        })),
        h(Field, { label: "Passwort" }, h("input", {
          style: inputStyle, type: "password", value: form.password || "", onChange: text("password"),
          placeholder: "leer lassen = unverändert", autoComplete: "new-password"
        })),
        h(Field, { label: "Kanal" }, h("input", {
          style: inputStyle, type: "number", value: form.channel, onChange: num("channel")
        })),
        h(Field, { label: "Stream-Pfad" }, h("input", {
          style: inputStyle, value: form.stream_path || "", onChange: text("stream_path")
        })),
        h(Field, { label: "Snapshot-Pfad" }, h("input", {
          style: inputStyle, value: form.snapshot_path || "", onChange: text("snapshot_path")
        })),
        h(Field, { label: "Notizen" }, h("input", {
          style: inputStyle, value: form.notes || "", onChange: text("notes")
        }))
      ),
      h("div", { style: { display: "flex", gap: "16px", flexWrap: "wrap", margin: "4px 0 10px" } },
        h("label", { style: { fontSize: "13px", display: "flex", gap: "6px", alignItems: "center" } },
          h("input", { type: "checkbox", checked: !!form.relay_mode, onChange: check("relay_mode") }),
          "Relay-Modus (RTSP)"),
        h("label", { style: { fontSize: "13px", display: "flex", gap: "6px", alignItems: "center" } },
          h("input", { type: "checkbox", checked: !!form.mock, onChange: check("mock") }),
          "Mock-Kamera (ohne Hardware)")
      ),
      error ? h("div", { style: { color: "var(--ui-danger, #d33)", fontSize: "12px", marginBottom: "6px" } }, error) : null,
      h("div", { style: { display: "flex", gap: "8px" } },
        h(Button, { onClick: save, disabled: saving }, saving ? "Speichern …" : "Speichern"),
        h(Button, { onClick: props.onCancel, disabled: saving }, "Abbrechen")
      )
    );
  }

  function CameraRow(props) {
    var d = props.device;
    var img = props.img;
    var loading = props.loading;
    var busy = props.busy;
    var onSnap = props.onSnap;
    var onEdit = props.onEdit;
    var onDelete = props.onDelete;
    var onTest = props.onTest;
    var test = props.test;

    var detail = [d.host, d.port ? ":" + d.port : "", d.stream_url || ""]
      .filter(Boolean)
      .join(" · ") || "kein Endpunkt";

    return h("div", {
      style: {
        border: "1px solid var(--ui-stroke-secondary, rgba(128,128,128,.25))",
        borderRadius: "8px",
        padding: "12px",
        marginBottom: "12px",
        background: "var(--ui-surface, transparent)"
      }
    },
      h("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
        h("strong", null, d.name),
        h(Badge, null, d.type),
        d.mock ? h(Badge, null, "mock") : null,
        d.uid ? h("span", { style: { fontSize: "11px", color: "var(--ui-text-secondary, #888)" } }, d.uid) : null
      ),
      h("div", { style: { color: "var(--ui-text-secondary, #888)", fontSize: "12px", marginTop: "4px" } }, detail),
      test
        ? h("div", {
            style: {
              marginTop: "6px",
              fontSize: "12px",
              color: test.reachable ? "var(--ui-success, #2a7)" : "var(--ui-danger, #d33)"
            }
          }, (test.reachable ? "✓ " : "✗ ") + (test.detail || ""))
        : null,
      h("div", { style: { marginTop: "8px", display: "flex", gap: "8px", flexWrap: "wrap" } },
        h(Button, { onClick: onSnap, disabled: loading || busy }, loading ? "Lade …" : "Snapshot"),
        h(Button, { onClick: onTest, disabled: busy }, "Test"),
        h(Button, { onClick: onEdit, disabled: busy }, "Bearbeiten"),
        h(Button, { onClick: onDelete, disabled: busy }, "Löschen")
      ),
      img
        ? h("img", {
            src: img,
            alt: d.name + " snapshot",
            style: { marginTop: "8px", maxWidth: "100%", borderRadius: "6px", display: "block" }
          })
        : null
    );
  }

  function ServicesCard(props) {
    var state = useState(null);
    var data = state[0], setData = state[1];
    var busyState = useState({});
    var busy = busyState[0], setBusy = busyState[1];
    var errState = useState(null);
    var error = errState[0], setError = errState[1];

    function load() {
      api("/services")
        .then(function (r) { setData(r); })
        .catch(function (err) { setError(errText(err)); });
    }
    useEffect(load, []);

    function act(service, action) {
      setBusy(function (prev) { var n = Object.assign({}, prev); n[service + action] = true; return n; });
      setError(null);
      apiJSON("POST", "/services/" + service + "/" + action, {})
        .then(function () { load(); })
        .catch(function (err) { setError(errText(err)); })
        .then(function () {
          setBusy(function (prev) { var n = Object.assign({}, prev); delete n[service + action]; return n; });
        });
    }

    if (error) return h(Card, null, h(CardContent, null, h("p", null, "Fehler: " + error)));
    if (!data) return h("div", null, "Lade Dienste …");

    var services = data.services || {};
    return h(Card, null,
      h(CardHeader, null, h(CardTitle, null, "Dienste")),
      h(CardContent, null,
        Object.keys(services).map(function (name) {
          var svc = services[name] || {};
          var units = svc.units || {};
          var active = !!svc.active;
          var enabled = Object.keys(units).every(function (u) { return !!units[u].enabled; });
          return h("div", {
            key: name,
            style: {
              border: "1px solid var(--ui-stroke-secondary, rgba(128,128,128,.25))",
              borderRadius: "8px",
              padding: "12px",
              marginBottom: "10px"
            }
          },
            h("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
              h("strong", null, SERVICE_LABELS[name] || name),
              h(Badge, null, active ? "läuft" : "gestoppt"),
              h(Badge, null, enabled ? "Autostart an" : "Autostart aus")
            ),
            h("div", { style: { fontSize: "12px", color: "var(--ui-text-secondary, #888)", marginTop: "4px" } },
              Object.keys(units).map(function (u) {
                var unit = units[u] || {};
                return u + ": " + (unit.active ? "aktiv" : "inaktiv");
              }).join(" · ")
            ),
            h("div", { style: { marginTop: "8px", display: "flex", gap: "8px", flexWrap: "wrap" } },
              h(Button, {
                onClick: function () { act(name, active ? "stop" : "start"); },
                disabled: busy[name + "start"] || busy[name + "stop"]
              }, active ? "Stoppen" : "Starten"),
              h(Button, {
                onClick: function () { act(name, enabled ? "disable" : "enable"); },
                disabled: busy[name + "enable"] || busy[name + "disable"]
              }, enabled ? "Autostart aus" : "Autostart an")
            )
          );
        })
      )
    );
  }

  function Page() {
    var devState = useState(null);
    var devices = devState[0], setDevices = devState[1];
    var cfgState = useState(null);
    var configInfo = cfgState[0], setConfigInfo = cfgState[1];
    var errState = useState(null);
    var error = errState[0], setError = errState[1];
    var imgState = useState({});
    var images = imgState[0], setImages = imgState[1];
    var loadState = useState({});
    var loading = loadState[0], setLoading = loadState[1];
    var formState = useState(null);
    var formDevice = formState[0], setFormDevice = formState[1];
    var busyState = useState({});
    var busy = busyState[0], setBusy = busyState[1];
    var testState = useState({});
    var tests = testState[0], setTests = testState[1];

    function reload() {
      return api("/devices")
        .then(function (r) {
          setDevices(Array.isArray(r.devices) ? r.devices : []);
          setError(null);
        })
        .catch(function (err) { setError(errText(err)); })
        .then(function () {
          api("/config").then(setConfigInfo).catch(function () { /* optional */ });
        });
    }
    useEffect(function () { reload(); }, []);

    function snap(id) {
      setLoading(function (prev) { var n = Object.assign({}, prev); n[id] = true; return n; });
      api("/snapshot/" + encodeURIComponent(id))
        .then(function (r) {
          setImages(function (prev) { var n = Object.assign({}, prev); n[id] = r.image || null; return n; });
        })
        .catch(function () {
          setImages(function (prev) { var n = Object.assign({}, prev); n[id] = null; return n; });
        })
        .then(function () {
          setLoading(function (prev) { var n = Object.assign({}, prev); n[id] = false; return n; });
        });
    }

    function test(id) {
      setBusy(function (prev) { var n = Object.assign({}, prev); n[id] = true; return n; });
      apiJSON("POST", "/devices/" + encodeURIComponent(id) + "/test", {})
        .then(function (r) {
          setTests(function (prev) { var n = Object.assign({}, prev); n[id] = r; return n; });
        })
        .catch(function (err) {
          setTests(function (prev) { var n = Object.assign({}, prev); n[id] = { reachable: false, detail: errText(err) }; return n; });
        })
        .then(function () {
          setBusy(function (prev) { var n = Object.assign({}, prev); delete n[id]; return n; });
        });
    }

    function edit(id) {
      var row = (devices || []).filter(function (d) { return d.id === id; })[0];
      if (!row) return;
      api("/devices/" + encodeURIComponent(id))
        .then(function (r) { setFormDevice(r.device); })
        .catch(function (err) { setError(errText(err)); });
    }

    function remove(id) {
      if (!window.confirm("Kamera '" + id + "' wirklich löschen?")) return;
      setBusy(function (prev) { var n = Object.assign({}, prev); n[id] = true; return n; });
      api("/devices/" + encodeURIComponent(id), { method: "DELETE" })
        .then(function () { reload(); })
        .catch(function (err) { setError(errText(err)); })
        .then(function () {
          setBusy(function (prev) { var n = Object.assign({}, prev); delete n[id]; return n; });
        });
    }

    var header = h(Card, null,
      h(CardHeader, null,
        h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", flexWrap: "wrap" } },
          h(CardTitle, null, "Kameras" + (devices ? " (" + devices.length + ")" : "")),
          h(Button, {
            onClick: function () { setFormDevice(formDevice ? null : emptyDevice()); }
          }, formDevice ? "Formular schließen" : "+ Neue Kamera")
        )
      ),
      h(CardContent, null,
        configInfo ? h("div", { style: { fontSize: "11px", color: "var(--ui-text-tertiary, #888)", marginBottom: "8px" } },
          "Konfiguration: " + (configInfo.target || configInfo.config)
          + (configInfo.is_example ? " (wird beim ersten Speichern angelegt)" : "")
          + (configInfo.writable ? "" : " (nicht schreibbar!)")) : null,
        formDevice ? h(DeviceForm, {
          initial: formDevice,
          onSaved: function () { setFormDevice(null); reload(); },
          onCancel: function () { setFormDevice(null); }
        }) : null,
        error ? h("p", { style: { color: "var(--ui-danger, #d33)" } }, "Fehler: " + error) : null,
        !devices ? h("p", null, "Lade Kameras …") :
          (!devices.length ? h("p", null, "Keine Kameras konfiguriert.") :
            devices.map(function (d) {
              return h(CameraRow, {
                key: d.id,
                device: d,
                img: images[d.id],
                loading: !!loading[d.id],
                busy: !!busy[d.id],
                test: tests[d.id],
                onSnap: function () { snap(d.id); },
                onTest: function () { test(d.id); },
                onEdit: function () { edit(d.id); },
                onDelete: function () { remove(d.id); }
              });
            })
          )
      )
    );

    return h("div", null, header, h(ServicesCard, null));
  }

  window.__HERMES_PLUGINS__.register("iwfcam4hermes", Page);
})();
