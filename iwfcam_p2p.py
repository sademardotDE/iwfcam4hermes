#!/usr/bin/env python3
"""High-level Python API for iWFCam P2P (libZGP2PComm.so)."""

import logging
from typing import Any, Optional

from .iwfcam_jni_stubs import JNI_FUNCTIONS

log = logging.getLogger("iwfcam_p2p")


class IWFCamP2P:
    """Python wrapper around iWFCam JNI functions (stubs on x86_64)."""

    def __init__(self):
        self._available = False
        self._functions = {name: None for name in JNI_FUNCTIONS}

    def is_available(self) -> bool:
        return self._available

    # --- Device management ---
    def add_device(self, uid: str, **kwargs) -> bool:
        log.info("add_device called for %s", uid)
        # Stub: would call AddNewP2PDevice via JNI
        return True

    def update_device(self, uid: str, **kwargs) -> bool:
        log.info("update_device called for %s", uid)
        return True

    def delete_device(self, uid: str) -> bool:
        log.info("delete_device called for %s", uid)
        return True

    # --- Info queries ---
    def req_dev_ip_info(self, uid: str) -> Optional[dict]:
        log.info("req_dev_ip_info for %s", uid)
        return None

    def set_dev_ip_info(self, uid: str, ip: str, port: int) -> bool:
        log.info("set_dev_ip_info for %s -> %s:%s", uid, ip, port)
        return True

    def req_dev_wifi_info(self, uid: str) -> Optional[dict]:
        log.info("req_dev_wifi_info for %s", uid)
        return None

    # --- Media control ---
    def req_av_media(self, uid: str, channel: int = 0) -> bool:
        log.info("req_av_media for %s channel %s", uid, channel)
        return True

    def stop_av_media(self, uid: str, channel: int = 0) -> bool:
        log.info("stop_av_media for %s channel %s", uid, channel)
        return True

    def send_talk_audio(self, uid: str, data: bytes) -> bool:
        log.info("send_talk_audio for %s (%d bytes)", uid, len(data))
        return True

    def keep_wakeup(self, uid: str) -> bool:
        log.info("keep_wakeup for %s", uid)
        return True

    # --- Status ---
    def get_dev_status(self, uid: str) -> Optional[str]:
        log.info("get_dev_status for %s", uid)
        return "unknown"

    def get_online_user_count(self, uid: str) -> int:
        log.info("get_online_user_count for %s", uid)
        return 0

    def get_dev_last_error(self, uid: str) -> Optional[str]:
        log.info("get_dev_last_error for %s", uid)
        return None

    # --- Listing ---
    def list_functions(self, pattern: str = "") -> list[str]:
        if pattern:
            return [f for f in self._functions if pattern.lower() in f.lower()]
        return list(self._functions.keys())


if __name__ == "__main__":
    api = IWFCamP2P()
    print("Available functions:", len(api.list_functions()))
    print("P2P functions:", len(api.list_functions("P2P")))
    print("add_device result:", api.add_device("TESTUID"))
    print("req_av_media result:", api.req_av_media("TESTUID"))
