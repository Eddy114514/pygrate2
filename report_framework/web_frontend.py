import argparse
import os

from flask import Flask

from routes.api_routes import api_bp
from routes.page_routes import pages_bp
from services.warning_payload_service import (
    build_warning_id as _build_warning_id,
    serialize_warnings_for_client as _serialize_warnings_for_client,
    warning_to_payload as _warning_to_payload,
)


DEFAULT_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["DEFAULT_PROJECT_ROOT"] = DEFAULT_PROJECT_ROOT
    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)
    return app


app = create_app()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    app.run(debug=False, port=args.port)
