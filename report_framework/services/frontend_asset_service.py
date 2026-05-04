import json
import os


def frontend_template_context() -> dict:
    vite_dev_server = os.environ.get("PYGRATE_VITE_DEV_SERVER", "").rstrip("/")
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "static",
        "frontend",
        ".vite",
        "manifest.json",
    )
    manifest = None
    if not vite_dev_server and os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    return {
        "vite_dev_server": vite_dev_server,
        "vite_manifest": manifest,
    }
