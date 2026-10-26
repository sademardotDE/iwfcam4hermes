from setuptools import setup, find_packages

setup(
    name="iwfcam4hermes",
    version="0.2.0",
    description="WiFi camera management plugin for Hermes (iWFCam & Z-IOT)",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "websocket-client>=1.6.0",
    ],
    python_requires=">=3.8",
)
