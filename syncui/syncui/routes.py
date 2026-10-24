"""Flask route definitions for syncui."""

from __future__ import annotations

import json as _json

from flask import Flask, current_app, jsonify, redirect, render_template, request, session, url_for

from syncui.daemon_client import DaemonClient, DaemonNotRunningError, DaemonError
from syncui.ipc import default_socket_address
from syncui.tomlio import dict_to_toml, toml_to_dict

def _provider_schemas() -> dict[str, dict]:
    try:
        return _client().get("/providers")
    except (DaemonNotRunningError, DaemonError):
        return {}


def _socket_address() -> str:
    return (
        session.get("daemon_socket")
        or current_app.config.get("DAEMON_SOCKET_DEFAULT")
        or default_socket_address()
    )


def _client() -> DaemonClient:
    return DaemonClient(_socket_address())


def register(app: Flask) -> None:
    app.add_url_rule("/", view_func=index)
    app.add_url_rule("/status", view_func=status_page)
    app.add_url_rule("/connect", view_func=connect, methods=["POST"])
    app.add_url_rule("/fragment/form", view_func=fragment_form, methods=["POST"])
    app.add_url_rule("/api/config", view_func=api_config_get, methods=["GET"])
    app.add_url_rule("/api/config", view_func=api_config_post, methods=["POST"])
    app.add_url_rule("/api/convert", view_func=api_convert, methods=["POST"])
    app.add_url_rule("/api/status", view_func=api_status, methods=["GET"])
    app.add_url_rule("/api/schemas", view_func=api_schemas, methods=["GET"])
    app.add_url_rule("/api/pairs/<pair_id>/sync", view_func=api_pair_sync, methods=["POST"])
    app.add_url_rule("/api/pairs/<pair_id>/pause", view_func=api_pair_pause, methods=["POST"])
    app.add_url_rule("/api/pairs/<pair_id>/resume", view_func=api_pair_resume, methods=["POST"])
    app.add_url_rule("/api/config/reload", view_func=api_config_reload, methods=["POST"])
    app.add_url_rule("/api/config/save", view_func=api_config_save, methods=["POST"])


def connect():
    address = request.form.get("address", "").strip()
    if address:
        session["daemon_socket"] = address
    else:
        session.pop("daemon_socket", None)
    return redirect(url_for("index"))


def index():
    config = None
    toml_str = ""
    daemon_down = False
    daemon_error = None

    try:
        config = _client().get("/config")
        toml_str = dict_to_toml(config)
    except DaemonNotRunningError as e:
        daemon_down = True
        daemon_error = str(e)
    except DaemonError as e:
        daemon_error = str(e)

    schemas = _provider_schemas()
    return render_template(
        "index.html",
        config=config,
        toml=toml_str,
        schemas=schemas,
        schemas_json=_json.dumps(schemas),
        daemon_down=daemon_down,
        daemon_error=daemon_error,
        current_socket=_socket_address(),
    )


def fragment_form():
    """Return just the form pane HTML for a config dict POSTed as JSON."""
    try:
        config = request.get_json(silent=True) or {}
    except Exception:
        return "bad request", 400
    return render_template(
        "_form_fragment.html",
        config=config,
        schemas=_provider_schemas(),
    )


def api_config_get():
    try:
        config_dict = _client().get("/config")
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status

    try:
        toml_str = dict_to_toml(config_dict)
    except Exception as e:
        toml_str = f"# Failed to render TOML: {e}"

    return jsonify({"json": config_dict, "toml": toml_str})


def api_config_post():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "request body must be JSON"}), 400

    config_dict = None

    if "toml" in body:
        try:
            config_dict = toml_to_dict(body["toml"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 422
    elif "json" in body:
        config_dict = body["json"]
    else:
        return jsonify({"error": "body must contain 'toml' or 'json' key"}), 400

    try:
        result = _client().post("/config/apply", body=config_dict)
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status

    try:
        toml_str = dict_to_toml(result)
    except Exception:
        toml_str = ""

    return jsonify({"json": result, "toml": toml_str})


def api_status():
    try:
        return jsonify(_client().get("/status"))
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status


def api_convert():
    """Convert between JSON dict and TOML string without touching the daemon."""
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "request body must be JSON"}), 400
    if "toml" in body:
        try:
            d = toml_to_dict(body["toml"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 422
        return jsonify({"json": d})
    if "json" in body:
        try:
            t = dict_to_toml(body["json"])
        except Exception as e:
            return jsonify({"error": str(e)}), 422
        return jsonify({"toml": t})
    return jsonify({"error": "body must contain 'toml' or 'json' key"}), 400


def api_schemas():
    return jsonify(_provider_schemas())


def status_page():
    daemon_error = None
    daemon_down = False
    pairs = []
    daemon_status = None

    try:
        daemon_status = _client().get("/status")
        pairs = _client().get("/pairs")
    except DaemonNotRunningError as e:
        daemon_down = True
        daemon_error = str(e)
    except DaemonError as e:
        daemon_error = str(e)

    return render_template(
        "status.html",
        daemon_status=daemon_status,
        pairs=pairs,
        daemon_down=daemon_down,
        daemon_error=daemon_error,
        current_socket=_socket_address(),
    )


def api_pair_sync(pair_id: str):
    try:
        _client().post(f"/pairs/{pair_id}/sync", body={})
        return jsonify({})
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status


def api_pair_pause(pair_id: str):
    try:
        _client().post(f"/pairs/{pair_id}/pause", body={})
        return jsonify({})
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status


def api_pair_resume(pair_id: str):
    try:
        _client().post(f"/pairs/{pair_id}/resume", body={})
        return jsonify({})
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status


def api_config_reload():
    try:
        _client().post("/config/reload", body={})
        return jsonify({})
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status


def api_config_save():
    try:
        _client().post("/config/save", body={})
        return jsonify({})
    except DaemonNotRunningError as e:
        return jsonify({"error": str(e), "daemon_down": True}), 503
    except DaemonError as e:
        return jsonify({"error": str(e)}), e.status
