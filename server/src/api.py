import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config_store import read_config, write_config
from .mqtt_client import device_states, mqtt_listener_loop, publish_command, publish_value

logger = logging.getLogger(__name__)

# AUTH_PASSWORD must be set; main.py exits early if it is missing
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")


def verify_auth(request: Request):
    """Require an authenticated session cookie. Raises 401 otherwise."""
    if not request.session.get("auth"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start MQTT listener in background
    task = asyncio.create_task(mqtt_listener_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)

# Session cookie config. Secret defaults to AUTH_PASSWORD so no extra env is required
# (changing the password invalidates existing sessions, which is acceptable).
SECRET_KEY = os.getenv("SECRET_KEY") or AUTH_PASSWORD
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(60 * 60 * 24 * 365)))  # 1 year
# Secure flag requires HTTPS. PWA/service-worker already require HTTPS, so default True.
# For local HTTP dev set COOKIE_SECURE=false.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() not in ("false", "0", "no")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="fp_session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=COOKIE_SECURE,
)

APP_TITLE = os.getenv("APP_TITLE", "Z2M Floorplan")


@app.get("/api/info")
def get_info():
    """Return public app metadata. No auth required."""
    return JSONResponse(content={"title": APP_TITLE})


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
    if not secrets.compare_digest(password.encode(), AUTH_PASSWORD.encode()):
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


@app.get("/api/config", dependencies=[Depends(verify_auth)])
def get_config():
    return JSONResponse(content=read_config())


@app.post("/api/config", dependencies=[Depends(verify_auth)])
async def post_config(request: Request):
    body = await request.json()
    write_config(body)
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


_static_path = os.path.join(os.path.dirname(__file__), "..", "static")

# --- App icon (home-screen / PWA) ---
# Custom icon is stored on the /data volume; falls back to the bundled default.
ICON_PATH = Path(os.getenv("ICON_PATH", "/data/icon.png"))
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


# Mount frontend static files last so /api/* routes take priority
if os.path.isdir(_static_path):
    app.mount("/", StaticFiles(directory=_static_path, html=True), name="static")
