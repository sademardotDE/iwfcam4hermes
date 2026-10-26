"""iwfcam4hermes plugin package."""

from .plugin import Camera, CameraType, load_config
from .camera_gui_plugin import CameraGUIPlugin, create_camera_gui_plugin

__all__ = ["Camera", "CameraType", "load_config", "CameraGUIPlugin", "create_camera_gui_plugin"]
