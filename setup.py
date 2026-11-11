from setuptools import setup

# Das Repository-Wurzelverzeichnis *ist* das Python-Paket ``iwfcam4hermes``
# (Hermes-Verzeichnis-Plugin mit plugin.yaml + __init__.py). Deshalb wird das
# Paket explizit auf "." gemappt; ein klassisches src-Layout gibt es hier nicht.
setup(
    name="iwfcam4hermes",
    version="0.3.0",
    description=(
        "Hermes plugin for WiFi camera management (iWFCam & Z-IOT): verified binary "
        "signaling, RTP/JPEG media, self-hosted receiver and a streaming GUI"
    ),
    author="sademar",
    license="MIT",
    url="https://github.com/sademardotDE/iwfcam4hermes",
    packages=["iwfcam4hermes"],
    package_dir={"iwfcam4hermes": "."},
    package_data={
        "iwfcam4hermes": [
            "plugin.yaml",
            "plugin.json",
            "config.example.json",
            "jpeg-huffman.bin",
            "docs/*.md",
        ],
    },
    include_package_data=True,
    install_requires=[
        "requests>=2.31.0",
        "websocket-client>=1.6.0",
    ],
    extras_require={
        "gui": ["opencv-python>=4.8", "pillow>=10.0"],
        "ble": ["bleak>=0.22"],
    },
    python_requires=">=3.9",
)
