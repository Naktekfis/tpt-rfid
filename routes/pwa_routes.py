"""Installable admin app (PWA): the manifest and the service worker, served
from the site root so the worker's scope covers /admin."""

from __future__ import annotations

from flask import Blueprint, current_app, send_from_directory


def create_pwa_blueprint() -> Blueprint:
    bp = Blueprint("pwa", __name__)

    @bp.route("/manifest.webmanifest")
    def manifest():
        return send_from_directory(
            current_app.static_folder,
            "manifest.webmanifest",
            mimetype="application/manifest+json",
        )

    @bp.route("/sw.js")
    def service_worker():
        response = send_from_directory(
            current_app.static_folder, "js/sw.js", mimetype="text/javascript"
        )
        response.headers["Cache-Control"] = "no-cache"
        return response

    @bp.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            current_app.static_folder, "icons/favicon-32.png", mimetype="image/png"
        )

    return bp
