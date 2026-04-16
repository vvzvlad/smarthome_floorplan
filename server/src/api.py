import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from .config_store import read_config, write_config
from .mqtt_client import device_states, mqtt_listener_loop, publish_command

logger = logging.getLogger(__name__)

# AUTH_PASSWORD must be set; main.py exits early if it is missing
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
AUTH_USERNAME = "admin"

security = HTTPBasic()


def verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Validate Basic Auth credentials. Raises 401 on mismatch."""
    username_ok = secrets.compare_digest(
        credentials.username.encode(), AUTH_USERNAME.encode()
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode(), AUTH_PASSWORD.encode()
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


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

APP_TITLE = os.getenv("APP_TITLE", "HA Floorplan")


@app.get("/api/info")
def get_info():
    """Return public app metadata. No auth required."""
    return JSONResponse(content={"title": APP_TITLE})


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
    Body: {"state": "ON"} or {"state": "OFF"}
    """
    body = await request.json()
    state = body.get("state", "").upper()
    if state not in ("ON", "OFF"):
        raise HTTPException(status_code=400, detail="state must be ON or OFF")
    await publish_command(entity_id, state)
    # Optimistically update in-memory state
    device_states[entity_id] = {"state": state}
    return JSONResponse(content={"ok": True})


# Mount frontend static files last so /api/* routes take priority
_static_path = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_path):
    app.mount("/", StaticFiles(directory=_static_path, html=True), name="static")
