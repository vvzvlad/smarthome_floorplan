import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import CachedStaticFiles

# Cache-Control values the policy emits.
IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"

# A representative /static directory prefix; only the suffix is load-bearing.
_BASE = "/srv/app/server/static"


# --------------------------------------------------------------------------- #
# 1) Pure unit test of the classifier (no filesystem)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("req_path", "file_path", "expected"),
    [
        # --- Fingerprinted -> True ------------------------------------------ #
        # Vite-hashed JS/CSS under assets/.
        ("assets/index-abc123.js", f"{_BASE}/assets/index-abc123.js", True),
        ("assets/index-abc123.css", f"{_BASE}/assets/index-abc123.css", True),
        # Workbox runtime carries a content hash in its filename.
        ("workbox-deadbeef.js", f"{_BASE}/workbox-deadbeef.js", True),
        # html-fallback shape: req_path is "." but the resolved file is under
        # assets/, so the "/assets/" substring alone must trigger True.
        (".", f"{_BASE}/assets/index-abc123.js", True),
        # --- NOT fingerprinted -> False ------------------------------------- #
        ("index.html", f"{_BASE}/index.html", False),
        # html=True index fallback: req_path "." resolving to index.html. This is
        # the most important negative case -- index.html must never be immutable.
        (".", f"{_BASE}/index.html", False),
        ("sw.js", f"{_BASE}/sw.js", False),
        ("sw.js.map", f"{_BASE}/sw.js.map", False),
        ("manifest.webmanifest", f"{_BASE}/manifest.webmanifest", False),
        ("registerSW.js", f"{_BASE}/registerSW.js", False),
        ("favicon.svg", f"{_BASE}/favicon.svg", False),
        ("pwa-192x192.png", f"{_BASE}/pwa-192x192.png", False),
        # Ends in .map, not .js -> a workbox sourcemap is NOT fingerprinted.
        ("workbox-deadbeef.js.map", f"{_BASE}/workbox-deadbeef.js.map", False),
    ],
)
def test_is_fingerprinted(req_path, file_path, expected):
    assert CachedStaticFiles._is_fingerprinted(req_path, file_path) is expected


# --------------------------------------------------------------------------- #
# 2) Integration test through TestClient with a temp static dir
# --------------------------------------------------------------------------- #
def _build_static_dir(tmp_path):
    """Create a minimal built-frontend layout under tmp_path and return it.

    Hermetic: the test never touches the real server/static/ dir (which does not
    exist in CI without a frontend build).
    """
    static = tmp_path / "static"
    assets = static / "assets"
    assets.mkdir(parents=True)
    files = {
        static / "index.html": "<!doctype html><title>app</title>",
        static / "sw.js": "// service worker",
        static / "sw.js.map": "{}",
        static / "manifest.webmanifest": "{}",
        static / "favicon.svg": "<svg/>",
        static / "registerSW.js": "// register",
        static / "workbox-deadbeef.js": "// workbox",
        assets / "index-abc123.js": "console.log(1)",
        assets / "index-abc123.css": "body{}",
    }
    for path, content in files.items():
        path.write_text(content)
    return static


@pytest.fixture()
def static_client(tmp_path):
    """A throwaway FastAPI app serving a fresh temp static dir via CachedStaticFiles."""
    static = _build_static_dir(tmp_path)
    app = FastAPI()
    app.mount("/", CachedStaticFiles(directory=str(static), html=True), name="static")
    return TestClient(app)


@pytest.mark.parametrize(
    ("route", "expected_cache_control"),
    [
        ("/index.html", NO_CACHE),
        ("/sw.js", NO_CACHE),
        ("/manifest.webmanifest", NO_CACHE),
        ("/favicon.svg", NO_CACHE),
        ("/registerSW.js", NO_CACHE),
        ("/assets/index-abc123.js", IMMUTABLE),
        ("/assets/index-abc123.css", IMMUTABLE),
        ("/workbox-deadbeef.js", IMMUTABLE),
    ],
)
def test_cache_control_header(static_client, route, expected_cache_control):
    resp = static_client.get(route)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == expected_cache_control


def test_root_index_is_never_immutable(static_client):
    # CRITICAL INVARIANT: html=True serves index.html for "/". index.html must
    # always be `no-cache` (never immutable) -- otherwise browsers pin a stale app
    # shell forever and the entire cache-busting fix is defeated.
    resp = static_client.get("/")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == NO_CACHE
