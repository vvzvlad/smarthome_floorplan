import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import Scope

from .config_store import read_config, write_config
from .mqtt_client import device_states, mqtt_listener_loop, publish_command, publish_value, topic_values, publish_raw, subscribed_read_topics, publishable_topics
from .settings import settings

logger = logging.getLogger(__name__)

_mqtt_task: "asyncio.Task | None" = None


def verify_auth(request: Request):
    """Require an authenticated session cookie. Raises 401 otherwise."""
    if not request.session.get("auth"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mqtt_task
    _mqtt_task = asyncio.create_task(mqtt_listener_loop())
    yield
    _mqtt_task.cancel()
    try:
        await _mqtt_task
    except asyncio.CancelledError:
        pass


async def _restart_mqtt_listener() -> None:
    """Cancel and respawn the MQTT listener so it resubscribes to the current config read topics.

    Awaits the cancelled task so its broker connection is fully closed before the new
    one connects — otherwise two clients with the same id briefly overlap (broker takeover).
    """
    global _mqtt_task
    old = _mqtt_task
    if old is not None and not old.done():
        old.cancel()
        try:
            await old
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    _mqtt_task = asyncio.create_task(mqtt_listener_loop())


app = FastAPI(lifespan=lifespan)

# Session cookie config. Secret defaults to AUTH_PASSWORD (settings.effective_secret_key)
# so no extra env is required (changing the password invalidates existing sessions,
# which is acceptable). The Secure flag requires HTTPS; PWA/service-worker already
# require HTTPS, so settings.cookie_secure defaults to True. For local HTTP dev set
# COOKIE_SECURE=false.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.effective_secret_key,
    session_cookie="fp_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.cookie_secure,
)

# Compress responses. A reverse proxy/CDN may already do this at the edge, but the
# app must not depend on it: with no CDN the otherwise ~46 KB bootstrap/config JSON
# would travel uncompressed. Added after SessionMiddleware so it sits outermost and
# compresses the final body; it skips bodies under minimum_size and honors
# Accept-Encoding, so clients without gzip support still get plain responses.
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.get("/api/info")
def get_info():
    """Return public app metadata. No auth required."""
    return JSONResponse(content={"title": settings.app_title})


@app.post("/api/login")
async def login(request: Request):
    """Validate the password and start an authenticated session."""
    # Reject malformed bodies (empty / non-JSON) with 400 instead of crashing with 500
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid body")
    # Treat a missing/non-string password as empty so it fails auth (401) rather than 500
    password = body.get("password", "") if isinstance(body, dict) else ""
    if not isinstance(password, str):
        password = ""
    if not secrets.compare_digest(password.encode(), settings.auth_password.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong password")
    request.session["auth"] = True
    return JSONResponse(content={"ok": True})


@app.post("/api/logout")
async def logout(request: Request):
    """Clear the session."""
    request.session.clear()
    return JSONResponse(content={"ok": True})


@app.get("/api/session")
def get_session(request: Request):
    """Public: report whether the current session is authenticated.

    Used by the frontend on startup to decide login vs app WITHOUT triggering
    the 401 path (which would reload-loop, since the HttpOnly cookie is invisible to JS).
    """
    return JSONResponse(content={"auth": bool(request.session.get("auth"))})


@app.get("/api/bootstrap")
def get_bootstrap(request: Request):
    """Public: one-shot startup payload. Reports auth status and, when authed,
    bundles config + device states + read-topic values so the frontend needs a
    single round-trip instead of four serial ones. Never 401s (like /api/session)."""
    authed = bool(request.session.get("auth"))
    payload = {"auth": authed, "title": settings.app_title}
    if authed:
        payload["config"] = read_config()
        payload["states"] = device_states
        payload["topics"] = topic_values
    return JSONResponse(content=payload)


@app.get("/api/config", dependencies=[Depends(verify_auth)])
def get_config():
    return JSONResponse(content=read_config())


@app.post("/api/config", dependencies=[Depends(verify_auth)])
async def post_config(request: Request):
    body = await request.json()
    old_topics = subscribed_read_topics(read_config())
    write_config(body)
    if subscribed_read_topics(body) != old_topics:
        await _restart_mqtt_listener()
    return JSONResponse(content={"ok": True})


@app.get("/api/states", dependencies=[Depends(verify_auth)])
def get_states():
    """Return last known state of all z2m devices."""
    return JSONResponse(content=device_states)


@app.get("/api/devices", dependencies=[Depends(verify_auth)])
def get_devices():
    """Return sorted list of known z2m device friendly names."""
    return JSONResponse(content=sorted(device_states.keys()))


@app.post("/api/entity/{entity_id:path}/command", dependencies=[Depends(verify_auth)])
async def post_command(entity_id: str, request: Request):
    """
    Accept a command for a device and forward it to MQTT.
    entity_id is the z2m friendly_name (may contain spaces, URL-encoded as %20).
    Body: {"state": "ON"} | {"state": "OFF"} or {"field": "brightness", "value": 128}
    """
    body = await request.json()
    # On/off command takes priority: {"state": "ON"|"OFF"}
    state = body.get("state")
    if isinstance(state, str) and state.strip():
        state = state.upper()
        if state not in ("ON", "OFF"):
            raise HTTPException(status_code=400, detail="state must be ON or OFF")
        await publish_command(entity_id, state)
        device_states[entity_id] = {"state": state}
        return JSONResponse(content={"ok": True})
    # Numeric value command: {"field": "brightness", "value": 128}
    field = body.get("field")
    value = body.get("value")
    if not isinstance(field, str) or not field:
        raise HTTPException(status_code=400, detail="field must be a non-empty string")
    # bool is a subclass of int in Python — reject it explicitly
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HTTPException(status_code=400, detail="value must be a number")
    await publish_value(entity_id, field, value)
    # Optimistically merge into in-memory state without clobbering other fields
    device_states.setdefault(entity_id, {})[field] = value
    return JSONResponse(content={"ok": True})


@app.get("/api/mqtt/topics", dependencies=[Depends(verify_auth)])
def get_mqtt_topics():
    """Return last raw values seen on the configured MQTT read topics."""
    return JSONResponse(content=topic_values)


@app.post("/api/mqtt/publish", dependencies=[Depends(verify_auth)])
async def post_mqtt_publish(request: Request):
    """Publish a raw value (no JSON) to an MQTT topic."""
    body = await request.json()
    topic = body.get("topic")
    value = body.get("value")
    if not isinstance(topic, str) or not topic.strip():
        raise HTTPException(status_code=400, detail="topic must be a non-empty string")
    if not isinstance(value, str):
        # Accept numbers too, coerce to text; reject everything else (incl. bool)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(status_code=400, detail="value must be a string or number")
        value = str(value)
    cfg = read_config()
    # Allow publishing only to topics configured by a number widget (write), a
    # button widget, a toggle widget (write), or a select widget (write) — never
    # arbitrary topics.
    if topic not in publishable_topics(cfg):
        raise HTTPException(status_code=403, detail="topic is not a configured publish topic")
    await publish_raw(topic, value)
    return JSONResponse(content={"ok": True})


_static_path = os.path.join(os.path.dirname(__file__), "..", "static")

# --- App icon (home-screen / PWA) ---
# Custom icon is stored on the /data volume; falls back to the bundled default.
ICON_PATH = Path(settings.icon_path)
_DEFAULT_ICON = Path(_static_path) / "apple-touch-icon-default.png"
MAX_ICON_BYTES = 2 * 1024 * 1024  # 2 MB upload limit
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@app.get("/apple-touch-icon.png")
def get_apple_touch_icon():
    """Public: serve the custom home-screen icon if uploaded, else the bundled default.

    Must stay unauthenticated: iOS fetches this without credentials when the user
    adds the site to the Home Screen.
    """
    target = ICON_PATH if ICON_PATH.exists() else _DEFAULT_ICON
    if not target.exists():
        raise HTTPException(status_code=404, detail="Icon not found")
    return FileResponse(
        target, media_type="image/png", headers={"Cache-Control": "no-cache"}
    )


@app.get("/api/icon", dependencies=[Depends(verify_auth)])
def get_icon_status():
    """Report whether a custom icon is currently set."""
    return JSONResponse(content={"custom": ICON_PATH.exists()})


@app.post("/api/icon", dependencies=[Depends(verify_auth)])
async def set_icon(request: Request):
    """Store an uploaded PNG (raw image/png body) as the custom icon."""
    data = await request.body()
    if len(data) > MAX_ICON_BYTES:
        raise HTTPException(status_code=413, detail="Icon too large")
    if not data.startswith(_PNG_MAGIC):
        raise HTTPException(status_code=400, detail="Icon must be a PNG image")
    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ICON_PATH, "wb") as f:
        f.write(data)
    return JSONResponse(content={"ok": True})


@app.delete("/api/icon", dependencies=[Depends(verify_auth)])
def delete_icon():
    """Remove the custom icon, reverting to the bundled default."""
    if ICON_PATH.exists():
        ICON_PATH.unlink()
    return JSONResponse(content={"ok": True})


class CachedStaticFiles(StaticFiles):
    """StaticFiles that emits explicit Cache-Control headers.

    Starlette's StaticFiles only sets ETag/Last-Modified, so browsers fall back to
    *heuristic* freshness (~10% of the file's age) for the app shell. That pins an
    installed PWA — especially an iOS standalone app, which resumes without a fresh
    navigation and so rarely runs a service-worker update check — to a stale build.

    Policy:
      * fingerprinted assets (Vite `assets/*`, hashed `workbox-*.js`) -> cache forever
        (`immutable`), since a content change always yields a new filename;
      * everything else (index.html, sw.js, manifest, icons, ...) -> `no-cache`, i.e.
        the client may store it but MUST revalidate (ETag) before reuse.
    """

    @staticmethod
    def _is_fingerprinted(req_path: str, file_path: str) -> bool:
        p = (file_path or req_path).replace("\\", "/")
        name = p.rsplit("/", 1)[-1]
        if "/assets/" in p or req_path.startswith("assets/"):
            return True
        # Workbox runtime is emitted with a content hash in its filename.
        return name.startswith("workbox-") and name.endswith(".js")

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        # For the html=True index fallback `path` is "."; use the real served file.
        file_path = str(getattr(response, "path", "") or "")
        if self._is_fingerprinted(path, file_path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


# Mount frontend static files last so /api/* routes take priority
if os.path.isdir(_static_path):
    app.mount("/", CachedStaticFiles(directory=_static_path, html=True), name="static")
