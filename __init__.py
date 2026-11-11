"""iwfcam4hermes — Hermes-Plugin für WiFi-Kameras (iWFCam & Z-IOT).

Hermes lädt dieses Paket als Verzeichnis-Plugin (``plugin.yaml`` + ``__init__.py``)
und ruft :func:`register` mit einem Plugin-Kontext auf. Die Registrierung ist
bewusst schlank: sie registriert nur Tools, Schemas und die ``hermes cameras``-CLI.
Teure Importe (Netzwerk, OpenCV, Tk) passieren erst in den Handlern.

Die öffentlichen Klassen/Funktionen der Vorgängerversionen bleiben als lazy
Re-Exports erhalten, damit bestehende Importe (``from iwfcam4hermes import
Camera``) weiter funktionieren, ohne beim Plugin-Laden alle Module zu importieren.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.7.0"

# name -> (Modul, Attribut); wird beim ersten Zugriff importiert.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "Camera": (".plugin", "Camera"),
    "CameraType": (".plugin", "CameraType"),
    "load_config": (".plugin", "load_config"),
    "fetch_snapshot": (".plugin", "fetch_snapshot"),
    "CameraManager": (".manager", "CameraManager"),
    "HermesPlugin": (".hermes_plugin", "HermesPlugin"),
    "create_plugin": (".hermes_plugin", "create_plugin"),
    "CameraGUIPlugin": (".camera_gui_plugin", "CameraGUIPlugin"),
    "create_camera_gui_plugin": (".camera_gui_plugin", "create_camera_gui_plugin"),
    "JpegRtpReceiver": (".rtp_receiver", "JpegRtpReceiver"),
    "RtpPacket": (".rtp_receiver", "RtpPacket"),
    "parse_rtp": (".rtp_receiver", "parse_rtp"),
    "load_dht_from_jpeg": (".rtp_receiver", "load_dht_from_jpeg"),
    "default_dht": (".rtp_receiver", "default_dht"),
    "MediaReceiver": (".media_receiver", "MediaReceiver"),
    "ZiotReceiverServer": (".ziot_receiver", "ZiotReceiverServer"),
    "ZIOTAdapter": (".ziota_adapter", "ZIOTAdapter"),
    "IWFCamAdapter": (".iwfcam_adapter", "IWFCamAdapter"),
    "IWFCamP2P": (".iwfcam_p2p", "IWFCamP2P"),
    "StreamProxy": (".stream_proxy", "StreamProxy"),
    "stun_binding": (".stun_client", "stun_binding"),
    "services": (".services", None),
    "config_store": (".config_store", None),
    "relay": (".relay", None),
}

__all__ = ["register", "__version__", *sorted(_LAZY_EXPORTS)]


def __getattr__(name: str) -> Any:
    """Lazy-Import der historischen Paket-Exports."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    from importlib import import_module

    module = import_module(module_name, __name__)
    value = module if attribute is None else getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


def register(ctx: Any) -> None:
    """Hermes-Plugin-Einstiegspunkt: Tools + CLI registrieren.

    Wird vom Hermes-Loader nach dem Import aufgerufen (auch im isolierten
    Capability-Probe von ``hermes plugins validate``). Darf daher weder Netzwerk
    noch Kamera-Hardware voraussetzen.
    """
    from .plugin_tools import TOOL_SCHEMAS, make_handlers, register_cli

    handlers = make_handlers(ctx)
    for name, schema in TOOL_SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="cameras",
            schema=schema,
            handler=handlers[name],
            emoji="📷",
        )
    register_cli(ctx)
