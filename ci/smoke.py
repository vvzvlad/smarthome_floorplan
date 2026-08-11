"""Smoke gate for the smarthome_floorplan image, run on the CI runner against an
already-built image.

Like the gate in 99bot_ng — and unlike the ones in token_checker and ukuetis_site, which are
piped into a container over stdin — this one runs OUTSIDE the image: it is a plain
`python3 ci/smoke.py` on the runner that drives `docker run` against the tag it is given in
$SMOKE_IMAGE. It has to be outside, because several of its checks are about the container as
a whole — how the image behaves with NO environment at all, what `docker inspect` says its
CMD and WORKDIR are, whether the port it publishes actually answers, and whether the
container is still alive when everything else is done — and none of those can be answered
from a process already running inside it.

The runner's job image (`docker.gitea.com/runner-images:ubuntu-latest`) ships
/usr/bin/python3; note that it ships `python3` and NOT a bare `python`, which is why both
workflows invoke this as `python3 ci/smoke.py`. Nothing beyond the standard library is
imported here.

What this gate can be, and what it cannot
-----------------------------------------
There IS a test suite in this repo — 198 pytest cases for the backend and a vitest suite for
the frontend — and both run in their own jobs before the image is built. That makes this
gate's job narrower and sharper than "does the code work": the tests already answer that, in
a checkout, against source files. What they cannot answer is whether the ARTEFACT that gets
deployed carries that code, is wired up the way the deployment expects, and comes up on its
own. Every check below is one of those, and every one of them is a way this image has a
realistic chance of shipping broken while all 198 tests stay green:

* (a) the required-variable guard still fires. `server/src/settings.py` declares
  `auth_password` and `mqtt_host` with no default, so `Settings()` raises a pydantic
  ValidationError at IMPORT time and the container cannot start. That is the intended
  behaviour and it must stay intended: a deployment redeployed without AUTH_PASSWORD has to
  die loudly rather than come up with an empty password. `restart: always` in the compose
  file means it will be restarted either way, so the exit code and that message are the only
  difference between "somebody dropped a variable out of the stack" and a service that is
  quietly wide open.
* (b) the image comes up and serves /api/info, with the APP_TITLE it was actually given.
  Checking that "something answered 200" would pass on a stale image, on a wrong image, and
  on an image whose settings never reached the app; requiring the title we passed in is what
  turns it into proof that this container is running THIS configuration.
* (c) every authenticated endpoint still answers 401 without a session. This service is
  published to the internet — `sh.asakusa-lab.cc`, Traefik on asakusa-infra, port 443 through
  the Keenetic at 37.204.142.243 — so a `Depends(verify_auth)` dropped from a route handler
  is the most expensive regression this repo can ship, and it is invisible in every other
  check here: the route would answer 200 and everything would look better than before.
* (d) the whole login chain works end to end: wrong password rejected, right password
  accepted, session cookie issued, and that cookie actually opening a protected route. It is
  the one check that exercises SessionMiddleware, `secrets.compare_digest` and `verify_auth`
  together, in the image, over real HTTP — the pytest suite drives the same code through
  Starlette's TestClient, which never builds a container and never sets a cookie over the
  wire.
* (e) the frontend is really in there. This is the single biggest risk of a two-stage
  Dockerfile: stage one runs `npm ci && npm run build`, stage two copies `/app/dist` into
  `./static/`, and if that build ever produces an empty or partial `dist` the image still
  builds, still starts, still answers every API call above — and serves a blank page. So the
  HTML is fetched, the asset URLs are read out of it, and each one is downloaded and required
  to be non-empty and of the right content type.
* (f) the app survives an unreachable broker. The whole gate rests on this: there is no MQTT
  broker in CI, and `mqtt_listener_loop()` is started as a background task by the lifespan
  handler, so the app is supposed to come up regardless and retry in a loop. If that ever
  stops being true — an exception escaping the loop, a broker connection moved into startup —
  the container would die and everything above would go red for a reason nobody could read
  off the failure. Checking it explicitly, and checking the logs say "reconnecting" rather
  than showing a traceback, is what makes that diagnosis land in one line.
* (g) the image's declared contract: CMD, WORKDIR, and the absence of an ENTRYPOINT. Every
  `docker run` in this file, and production itself, depends on the image's own command being
  the thing that runs.

Nothing here holds a credential or reaches an external service. The password is invented by
this file and passed in as AUTH_PASSWORD, the MQTT host points at a `.invalid` name, which
RFC 2606 reserves so no resolver can ever answer it, and the published port is bound to
127.0.0.1 on the runner. A gate that needed the real AUTH_PASSWORD could not run on a pull
request at all, and one that reddened on somebody else's outage is a gate everybody learns to
ignore.

Two properties matter and are easy to lose, so they are stated where they can be checked:

* Failures leave through SystemExit, never `assert`. Asserts vanish under PYTHONOPTIMIZE=1,
  which would silently turn this gate permanently green.
* Every check runs before anything is reported, so one run shows the full extent of the
  breakage instead of only the first broken thing. A check that CANNOT run reports itself as
  FAILED; it is never quietly skipped, which is the classic way a gate keeps reporting
  success while proving less and less.
"""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

# The tag to test. Required rather than defaulted: a default would let a mistyped `env:`
# block in a workflow silently gate some other image that happens to be on the daemon.
IMAGE_ENV = "SMOKE_IMAGE"
# Base name for every container this gate starts. The workflows put the run id in it, because
# the runner has a single docker daemon shared by every repository in the fleet and two
# concurrent runs must not collide on a name.
# Required, exactly like the tag above, and for two reasons that both end in silence rather
# than in an error — see the message in main() where it is enforced.
NAME_ENV = "SMOKE_NAME"

# The short-lived guard container is named too, not left to docker's random name generator,
# and the reason is the one case that matters: `--rm` fires when a container EXITS, and a
# container that hangs never does. `subprocess` hitting its timeout kills the docker CLIENT on
# the runner; the container it started stays behind on the shared daemon. With no name nobody
# could ever remove it — not remove_container() here, not the workflow's `if: always()` step,
# because neither would know what to remove — and it would go on pinning the image, so the
# `docker rmi` at the end of the job would fail too, be swallowed by its `|| true`, and leave
# both a container and a few hundred MB of image on the daemon the whole fleet shares.
# Kept in step with the suffix list in both workflows' cleanup steps: if you move one, move
# the other.
GUARD_SUFFIX = "-guard"

# The Dockerfile's WORKDIR, its CMD, and where the built frontend lands. Hardcoded rather than
# read back out of the image: these are the contract between this repo and its image, so a
# Dockerfile that quietly moves them has to go red here and be looked at, not be politely
# followed.
APP_DIR = "/app"
EXPECTED_CMD = ["python", "main.py"]
STATIC_DIR = "/app/static"
INDEX_PATH = "/app/static/index.html"

# The port `server/main.py` binds inside the container: uvicorn on 0.0.0.0:${PORT:-8000}. PORT
# is deliberately NOT passed by this gate, so what gets exercised is the same default the
# Dockerfile, the compose file and the Traefik service port all assume.
CONTAINER_PORT = 8000

# The host port is chosen by DOCKER, not by this file, and not by "find a free port and bind it
# later" either. `-p 127.0.0.1::8000` asks the daemon for an ephemeral host port and binds it
# in the same operation, so there is no window between picking a number and using it — which is
# exactly the window a fixed port, or a port probed from python, would leave open. It matters
# here specifically: this daemon is shared by every repository on the runner, two runs of this
# very gate can overlap (a push to main and a PR check), and a fixed port would make the second
# one fail on "address already in use" — a red gate caused by nothing but scheduling, which is
# the fastest way to teach everybody to re-run until green. Binding to 127.0.0.1 rather than
# 0.0.0.0 keeps the smoke container off the runner's network interfaces for its lifetime.
PUBLISH_SPEC = "127.0.0.1::{}".format(CONTAINER_PORT)

# The two variables `Settings` declares without a default, spelled exactly as pydantic reports
# them: it prints FIELD names, which are lowercase, not the SCREAMING_CASE of the environment.
# Check (a) requires both to be named, one row each, so a guard that lost one of them cannot
# hide behind the other still firing.
REQUIRED_FIELDS = ["auth_password", "mqtt_host"]

# The environment the long-lived container runs with. Every value is invented here:
#   * AUTH_PASSWORD is what check (d) logs in with, so the gate needs no real credential and
#     can run on a pull request;
#   * MQTT_HOST points at a `.invalid` name, reserved by RFC 2606, so DNS cannot resolve it and
#     the container cannot reach a real broker even by accident. That is what makes check (f)
#     decidable rather than dependent on whether some broker happens to be reachable;
#   * COOKIE_SECURE=false because `cookie_secure` defaults to True and a Secure cookie is not
#     stored over plain http. Without it check (d) would fail on a perfectly good image, and
#     for a reason that reads like broken authentication;
#   * APP_TITLE is deliberately NOT the default "Z2M Floorplan" — check (b) reads it back out
#     of /api/info, and a value equal to the default would prove nothing at all: the response
#     would be identical whether the variable arrived or was silently dropped.
SMOKE_PASSWORD = "smoke-not-a-real-password"
WRONG_PASSWORD = "smoke-definitely-the-wrong-password"
UNREACHABLE_MQTT_HOST = "mqtt.smoke.invalid"
SMOKE_TITLE = "smoke-app-title-4f2a"

# The cookie SessionMiddleware is configured with in server/src/api.py. Named here because
# check (d) does its own cookie handling rather than using http.cookiejar: one header in, one
# header out, and a rename of this cookie should be a finding rather than a silent pass.
SESSION_COOKIE = "fp_session"

# Every route that carries `Depends(verify_auth)` and is reachable with a plain GET. POST and
# DELETE routes are deliberately absent: `/api/config`, `/api/icon` and `/api/mqtt/publish`
# also have write handlers behind the same dependency, but probing those with an unauthenticated
# request only proves the same 401, while a bug in this file would then be writing to a
# container. The GET half of each pair is the honest place to ask the question.
PROTECTED_PATHS = [
    "/api/config",
    "/api/states",
    "/api/devices",
    "/api/mqtt/topics",
    "/api/icon",
]

# What `read_config()` returns for a container with no config file yet — which is every
# container this gate starts, since nothing mounts a volume. Checking for this key rather than
# for the whole document keeps the check honest: it proves the body is the config document the
# frontend consumes, and not a JSON error object or an empty `{}` that any handler could return.
CONFIG_SHAPE_KEY = "entities"

# The stable half of the line `mqtt_listener_loop()` logs when a connection attempt fails:
#   logger.warning("MQTT connection lost: %s. Reconnecting in %ss...", e, RECONNECT_DELAY)
# Matched on the word rather than on the whole sentence, because the exception text in the
# middle is aiomqtt's and changes with its version, while "Reconnecting in" is this repo's own
# wording and is the thing that has to keep being true.
RECONNECT_MARKER = "Reconnecting in"

# The first line of a python traceback. Its presence in the logs of a container that is
# nonetheless up means the reconnect loop is NOT what is happening — something is escaping and
# being printed by asyncio or uvicorn — and check (f) would otherwise pass on it, since the
# container really is running. This is the one check here that can go red on something
# harmless; that is the direction to be wrong in, and it is cheap to look at.
TRACEBACK_MARKER = "Traceback (most recent call last)"

# The content types a working build can legitimately serve for each kind of asset. A SET rather
# than one exact string on purpose: Starlette derives these from python's `mimetypes`, whose
# answer for `.js` has changed across releases (application/javascript -> text/javascript), and
# a base-image bump is not a reason to redden this gate. What IS a finding is a stylesheet
# served as text/html — which is exactly what an SPA fallback does when the file is missing.
CONTENT_TYPES = {
    ".js": ("text/javascript", "application/javascript", "application/x-javascript"),
    ".css": ("text/css",),
}

# Read out of index.html: `src="..."` and `href="..."` ending in .js or .css. Vite emits both
# with `base: './'`, so they arrive as `./assets/index-<hash>.js` and are normalised below.
ASSET_PATTERN = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+\.(?:js|css))["']""", re.I)

# How many assets are downloaded. A working build emits two or three; the cap exists so a
# generated index.html that somehow references a hundred files cannot turn this gate into a
# ten-minute download loop, and it is what the timeout arithmetic below is computed against.
MAX_ASSETS = 8

# Bounds. Every docker call gets one, because a gate that hangs is worse than a gate that
# fails: it holds a slot on a runner the whole fleet queues for until the step timeout kills
# it, and a killed step never runs its cleanup.
# The numbers are generous against the real cost — this image starts and answers in a couple of
# seconds — and are sized for a shared runner under load right after a build. Their worst-case
# SUM is what the smoke step's `timeout-minutes` in both workflows has to exceed, so it is
# spelled out here, in the order the calls actually happen:
#   30 (inspect config) + 30 (rm guard) + 90 (guard run) + 30 (rm main) + 60 (run -d)
#   + 30 (docker port) + 65 (readiness poll: 60 budget + one 5 s request in flight)
#   + 25 (5 protected routes x 5 s) + 15 (3 login-chain requests x 5 s)
#   + 45 (GET / plus up to 8 assets x 5 s) + 60 (docker exec static probe)
#   + 45 (reconnect poll: 30 budget + one 15 s `docker logs` in flight)
#   + 30 (inspect state) + 30 (rm main, in the finally)
#   = 585 s, a little under 10 minutes. Both workflows allow 12.
# Two of those `rm`s are pre-run cleanups: every container this gate starts is removed by name
# before it is started, so a re-run from the UI — which keeps the same run id, hence the same
# $SMOKE_NAME — cannot die on "name already in use".
INSPECT_TIMEOUT = 30
REMOVE_TIMEOUT = 30
GUARD_TIMEOUT = 90
START_TIMEOUT = 60
PORT_TIMEOUT = 30
EXEC_TIMEOUT = 60
LOGS_TIMEOUT = 15

# The readiness poll, bounded in WALL CLOCK rather than in attempts: each attempt is an HTTP
# request with its own 5 s timeout, so an attempt-counted bound would multiply into minutes the
# moment the container got slow. 60 s is roughly twenty times what this app needs — uvicorn is
# listening within a second or two of the interpreter starting — and the 0.5 s pause keeps a
# fast container from waiting on us.
READY_BUDGET = 60
READY_PAUSE = 0.5
HTTP_TIMEOUT = 5

# The reconnect-marker poll, bounded the same way and for the same reason: each attempt shells
# out to `docker logs`, whose own timeout is 15 s. The first warning is logged as soon as the
# first connection attempt fails, and with an unresolvable host that is a DNS failure rather
# than a connect timeout, so it arrives within a second; RECONNECT_DELAY in the app is 5 s, so
# 30 s covers several full turns of the loop.
RECONNECT_BUDGET = 30
RECONNECT_PAUSE = 0.5

# How much of an unexpected output reaches the log. Container logs can run to thousands of
# lines when something loops, and an unbounded dump would bury the verdict.
EXCERPT_CHARS = 4000

# Run inside the container with `docker exec`, to answer the one question about the filesystem
# that HTTP cannot: is the built frontend actually on disk where the app mounts it from. It has
# to be a separate look, because Starlette's StaticFiles is mounted with `html=True` — a
# request for a missing path falls back to index.html instead of 404ing, so "GET /assets/x.js
# answered 200" and "the file exists" are genuinely different statements. Printed as one JSON
# line so a failure carries the directory listing that explains it.
STATIC_PROBE = (
    "import json, os; "
    "index = {index!r}; "
    "static = {static!r}; "
    "print(json.dumps({{"
    "'index_exists': os.path.isfile(index), "
    "'index_size': os.path.getsize(index) if os.path.isfile(index) else 0, "
    "'entries': sorted(os.listdir(static))[:40] if os.path.isdir(static) else None"
    "}}))"
).format(index=INDEX_PATH, static=STATIC_DIR)


def excerpt(text):
    """Bound what reaches the log, and say so when something was cut."""
    if text is None:
        return ""
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[:EXCERPT_CHARS] + "\n[... truncated at {} characters]".format(EXCERPT_CHARS)


def describe(error):
    return "{}: {}".format(type(error).__name__, error)


def docker(args, timeout):
    """Run a docker command.

    Returns (status, output) with stderr folded into stdout, because everything here is read
    by a human out of a CI log where the interleaving is the useful part. A status of None
    means the command produced no exit code at all — it timed out, or docker is not there —
    and `output` then explains which.
    """
    argv = ["docker"] + args
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True)
    except FileNotFoundError:
        return None, (
            "`docker` is not on PATH. This gate drives the daemon from the runner, so it "
            "cannot run anywhere the docker CLI is missing")
    except subprocess.TimeoutExpired as error:
        return None, "`{}` did not finish within {} s. Output so far:\n{}".format(
            " ".join(argv), timeout, excerpt(error.output))
    return completed.returncode, completed.stdout or ""


def remove_container(name):
    """Best effort. Never the reason a check fails; the workflow cleans up too."""
    docker(["rm", "-f", name], REMOVE_TIMEOUT)


def http(url, method="GET", body=None, cookie=None):
    """One HTTP request. Returns (status, headers, body_bytes, reason).

    A 4xx or a 5xx is an ANSWER here, not an error: `verify_auth` returning 401 is the single
    most important thing this gate checks, so an HTTPError is unwrapped into a status like any
    other rather than being raised. `reason` is set only when there was no answer at all —
    connection refused, timeout, a half-closed socket — and the status is then None.

    No Accept-Encoding header is sent, deliberately: urllib does not add one, so
    GZipMiddleware leaves the body alone and everything below can read it without
    decompressing. Adding one here would silently turn every body comparison into a
    comparison against gzip bytes.
    """
    headers = {}
    if cookie is not None:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.status, response.headers, response.read(), None
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read(), None
    except Exception as error:
        return None, None, b"", describe(error)


def session_cookie(headers):
    """The `fp_session=<value>` pair out of the response's Set-Cookie headers, or None.

    Only the name=value part is kept: the attributes after the first `;` (Path, HttpOnly,
    SameSite, and Max-Age) are instructions to a browser, and sending them back in a Cookie
    header is not what a browser does.
    """
    if headers is None:
        return None
    for value in headers.get_all("Set-Cookie") or []:
        pair = value.split(";", 1)[0].strip()
        if pair.startswith(SESSION_COOKIE + "="):
            return pair
    return None


def content_type_of(headers):
    """The bare media type, without the `; charset=utf-8` a text response carries."""
    if headers is None:
        return ""
    return (headers.get("Content-Type") or "").split(";")[0].strip().lower()


def check_image_contract(image):
    """(g) What the image DECLARES: its command, where it runs, and that nothing wraps them."""
    rows = []
    status, output = docker(
        ["inspect", "--format", "{{json .Config}}", image], INSPECT_TIMEOUT)
    if status != 0:
        rows.append((
            "docker inspect {}".format(image),
            "exited {} — the tag does not exist on this daemon, so the build step and this "
            "step disagree about what was built. Output:\n{}".format(
                status, excerpt(output))))
        return rows
    try:
        config = json.loads(output)
    except ValueError as error:
        rows.append((
            "parse the image config of {}".format(image),
            "docker inspect returned something that is not JSON ({}): {}".format(
                error, excerpt(output))))
        return rows

    cmd = config.get("Cmd")
    rows.append((
        "the image's CMD is {}".format(EXPECTED_CMD),
        None if cmd == EXPECTED_CMD else (
            "it is {!r}. Every container this gate starts runs the image's own command, and "
            "so does production — a silent change here means the checks below and the "
            "deployment are describing two different programs".format(cmd))))

    # An ENTRYPOINT would prepend itself to the CMD above, so `docker run <image>` would no
    # longer be `python main.py` and check (a)'s verdict would be about something else
    # entirely. There is none today, and this is what keeps it that way.
    entrypoint = config.get("Entrypoint")
    rows.append((
        "the image declares no ENTRYPOINT, so its CMD is the whole command line",
        None if not entrypoint else (
            "it declares {!r}, which is prepended to the CMD. Every `docker run` in this gate "
            "now executes something other than what it reports".format(entrypoint))))

    working_dir = config.get("WorkingDir")
    rows.append((
        "the image's WORKDIR is {}".format(APP_DIR),
        None if working_dir == APP_DIR else (
            "it is {!r}. The CMD is the relative path {!r}, and the app resolves `src/`, "
            "`static/` and the `data/` volume mount point against the working directory too "
            "— moving it breaks all four at once".format(working_dir, EXPECTED_CMD[1]))))

    return rows


def check_missing_env_guard(image, name):
    """(a) Run the image with NO environment at all: it must die, and name both variables.

    This is the check that cannot live inside the container, and the one that most directly
    describes a real deployment failure — the stack redeployed without AUTH_PASSWORD. The
    mechanism is `Settings()` at the bottom of server/src/settings.py: it runs at import time,
    `auth_password` and `mqtt_host` have no defaults, so pydantic raises a ValidationError
    before uvicorn is ever reached.

    That it fires at all depends on the image carrying no `.env` file — `SettingsConfigDict`
    names one — and it does not: the Dockerfile's final stage copies only requirements.txt,
    main.py, src/ and the built frontend, and `.dockerignore` lists `.env` besides. A future
    Dockerfile that copied the repo root wholesale would break this guard in production
    without breaking a single test, and this check is what would notice.

    The image's own CMD is kept — no `-e`, no override. That is safe to run to completion here
    precisely because the guard makes it terminate on its own; there is no restart loop inside
    this image to hang on.

    `--rm` AND a name: the flag covers the container that exits, the name covers the one that
    does not. See GUARD_SUFFIX above for why the second half is not redundant.
    """
    rows = []
    target = "`docker run --rm {}` with no environment at all".format(image)
    # A re-run from the UI reuses the run id, so it reuses this name too, and a previous
    # attempt killed by the step timeout may have left the container behind. A no-op when it
    # did not.
    remove_container(name)
    status, output = docker(["run", "--rm", "--name", name, image], GUARD_TIMEOUT)
    if status is None:
        rows.append((target, output))
        return rows, output
    if status == 0:
        rows.append((target, (
            "it exited 0. The required-variable guard did not fire, so a stack redeployed "
            "without AUTH_PASSWORD would come up looking perfectly healthy — with an app "
            "whose login endpoint compares against whatever `auth_password` ended up being. "
            "Output:\n{}".format(excerpt(output)))))
        return rows, output
    rows.append(("{} exits non-zero (got {})".format(target, status), None))

    # A non-zero exit on its own is NOT enough, and this is the whole reason the output is
    # matched too: a typo in an import, a syntax error, a missing wheel — all of them exit
    # non-zero, and all of them would make this check pass while proving nothing about the
    # guard. Pydantic's ValidationError names the FIELDS it is missing, one per line, and
    # those names are the contract with the deployment.
    # One row per variable, not one row for both: a guard that lost `mqtt_host` (say, by
    # someone giving it a default "localhost") would still fire on `auth_password`, and a
    # single combined check would go on reporting success for a service that now silently
    # points its broker connection at itself.
    for field in REQUIRED_FIELDS:
        rows.append((
            "...and its output names the missing field {!r}".format(field),
            None if field in output else (
                "nothing in the output mentions it. The image exited {}, but either this is "
                "not the validation guard firing — it is the app dying of something else "
                "before it got there — or {!r} has quietly acquired a default and is no "
                "longer required at all. Output:\n{}".format(
                    status, field, excerpt(output)))))
    return rows, output


def start_container(image, name):
    """Start the long-lived container and find the host port docker gave it.

    Returns (rows, base_url, output). `base_url` is None when there is nothing to talk to, and
    every check that needed it then reports itself FAILED rather than being skipped.

    Started with the image's own CMD — no `--entrypoint`, which does not merely replace the
    entrypoint but also DROPS the image's CMD, making "does the image's own command bring the
    app up" unanswerable, and that is most of what checks (b) through (f) are about.
    """
    rows = []
    remove_container(name)
    status, output = docker(
        [
            "run", "-d", "--name", name,
            "-p", PUBLISH_SPEC,
            "-e", "AUTH_PASSWORD=" + SMOKE_PASSWORD,
            "-e", "MQTT_HOST=" + UNREACHABLE_MQTT_HOST,
            "-e", "COOKIE_SECURE=false",
            "-e", "APP_TITLE=" + SMOKE_TITLE,
            image,
        ],
        START_TIMEOUT)
    target = "`docker run -d` starts a container of {}".format(image)
    if status is None:
        rows.append((target, output))
        return rows, None, output
    if status != 0:
        rows.append((target, "`docker run -d` exited {}:\n{}".format(
            status, excerpt(output))))
        return rows, None, output
    rows.append((target, None))

    # The host port is read back from the daemon rather than assumed, which is the other half
    # of letting docker choose it: this is the only place that learns which port was bound.
    port_target = "`docker port` reports the host port bound to {}/tcp".format(CONTAINER_PORT)
    status, port_output = docker(
        ["port", name, "{}/tcp".format(CONTAINER_PORT)], PORT_TIMEOUT)
    if status != 0 or not port_output.strip():
        rows.append((port_target, (
            "it exited {} with {!r}. The container is running but nothing is published, so "
            "the image no longer EXPOSEs or binds {} — which is the port uvicorn listens on, "
            "the port the compose file's Traefik service label names, and the port every "
            "check below talks to".format(status, port_output.strip(), CONTAINER_PORT))))
        return rows, None, output
    # `docker port` prints one mapping per line, as `127.0.0.1:49154`. IPv6 mappings are
    # possible in principle and are why the split is on the LAST colon rather than the first.
    mapping = port_output.strip().splitlines()[0].strip()
    host_port = mapping.rsplit(":", 1)[-1]
    if not host_port.isdigit():
        rows.append((port_target, (
            "it printed {!r}, which does not end in a port number".format(mapping))))
        return rows, None, output
    rows.append(("{} -> {}".format(port_target, mapping), None))
    return rows, "http://127.0.0.1:{}".format(host_port), output


def check_info(base_url):
    """(b) Wait for /api/info, then require it to carry the APP_TITLE we passed in."""
    rows = []
    target = "GET /api/info answers 200 (bounded at {} s)".format(READY_BUDGET)
    if base_url is None:
        # Never silently skipped. A check that cannot run is a FAILED check, otherwise the
        # gate quietly shrinks to whatever still happens to work.
        rows.append((target, "not attempted: the container never gave us an address"))
        rows.append(("/api/info reports the APP_TITLE the container was given", (
            "not attempted: the container never gave us an address")))
        return rows

    deadline = time.monotonic() + READY_BUDGET
    status = None
    body = b""
    reason = "no attempt was made"
    while True:
        status, _, body, reason = http(base_url + "/api/info")
        if status == 200:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(READY_PAUSE)

    if status != 200:
        # The LAST reason is reported, not the first: the first is almost always "connection
        # refused" from the moment before uvicorn had bound, which describes nothing. The last
        # one is the state the endpoint was still in when the budget ran out.
        rows.append((target, (
            "it never did in {} s. Last answer: status {}, {}. The container is a python that "
            "started — check (a) proves the interpreter and the import chain work — so what "
            "failed is uvicorn binding {} or the app importing".format(
                READY_BUDGET, status, reason or "no transport error", CONTAINER_PORT)))
        )
        rows.append(("/api/info reports the APP_TITLE the container was given", (
            "not attempted: /api/info never answered 200")))
        return rows
    rows.append((target, None))

    title_target = "/api/info reports the APP_TITLE the container was given ({!r})".format(
        SMOKE_TITLE)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        rows.append((title_target, "200 but the body is not JSON ({}): {!r}".format(
            error, body[:200])))
        return rows
    if not isinstance(payload, dict):
        rows.append((title_target, "200 but the body is JSON and not an object: {!r}".format(
            payload)))
        return rows
    # This is the check that separates "something answered" from "THIS container, with THIS
    # configuration, answered". APP_TITLE has a default, so a container that never saw the
    # variable answers 200 with a perfectly plausible title — and every other check in this
    # file would still pass on it.
    rows.append((title_target, None if payload.get("title") == SMOKE_TITLE else (
        "it reports {!r} instead. Either the environment this gate passed did not reach the "
        "application — which would mean nothing else here is testing the configuration it "
        "thinks it is — or /api/info stopped reading settings.app_title".format(
            payload.get("title")))))
    return rows


def check_protected(base_url):
    """(c) Every authenticated route must answer 401 without a session."""
    rows = []
    for path in PROTECTED_PATHS:
        target = "GET {} without a session answers 401".format(path)
        if base_url is None:
            rows.append((target, "not attempted: the container never gave us an address"))
            continue
        status, _, body, reason = http(base_url + path)
        if status is None:
            rows.append((target, "no answer at all: {}".format(reason)))
            continue
        if status == 401:
            rows.append((target, None))
            continue
        # 200 is the finding this whole check exists for and is called out separately, because
        # it is the only status that means the route is now OPEN. Everything else is a broken
        # route, which is bad but not a disclosure.
        if status == 200:
            rows.append((target, (
                "it answered 200. This route is serving data to anyone who asks, and the "
                "service is published on the public internet at sh.asakusa-lab.cc — a "
                "`Depends(verify_auth)` has been dropped from its handler. Body: {!r}".format(
                    body[:200]))))
            continue
        rows.append((target, (
            "it answered {}. Not a disclosure, but not the contract either: the frontend "
            "treats 401 as 'show the login screen', and any other status leaves it stuck. "
            "Body: {!r}".format(status, body[:200]))))
    return rows


def check_login_chain(base_url):
    """(d) Wrong password rejected, right password accepted, and the cookie really opens a door.

    Deliberately end to end rather than three independent probes: what breaks in this area is
    the seam between the parts — SessionMiddleware signing a cookie the app cannot verify, a
    `secrets.compare_digest` comparing against the wrong thing, `verify_auth` reading a key
    the login handler never set. Each half looks fine on its own, and the pytest suite drives
    all of it through Starlette's TestClient, which never puts a cookie on the wire.
    """
    rows = []
    wrong_target = "POST /api/login with the wrong password answers 401"
    right_target = "POST /api/login with the right password answers 200"
    cookie_target = "...and sets a {} session cookie".format(SESSION_COOKIE)
    reuse_target = "GET /api/config with that cookie answers 200"
    shape_target = "...with a JSON object carrying {!r}".format(CONFIG_SHAPE_KEY)
    if base_url is None:
        for target in (wrong_target, right_target, cookie_target, reuse_target, shape_target):
            rows.append((target, "not attempted: the container never gave us an address"))
        return rows

    body = json.dumps({"password": WRONG_PASSWORD}).encode("utf-8")
    status, headers, payload, reason = http(base_url + "/api/login", "POST", body)
    if status is None:
        rows.append((wrong_target, "no answer at all: {}".format(reason)))
    elif status == 200:
        # The worst outcome in this file after an open route: the password check is not
        # checking. `secrets.compare_digest` against an empty or None `auth_password` would do
        # exactly this, and so would a handler that stopped comparing at all.
        rows.append((wrong_target, (
            "it answered 200 and issued a session. The password comparison is not rejecting "
            "anything, which makes every protected route above reachable by anyone who posts "
            "a login")))
    elif status != 401:
        rows.append((wrong_target, "it answered {}: {!r}".format(status, payload[:200])))
    else:
        rows.append((wrong_target, None))
    # A wrong password must not leave a usable cookie behind either. Checked here rather than
    # as its own row because it is the same finding as the 200 above, arriving by a different
    # route: a handler that sets the session before comparing.
    stray_target = "POST /api/login with the wrong password sets no session cookie"
    if status is None:
        # Not "there was no cookie, so this passed": there was no answer, so the question was
        # never asked. Reported as a failure for the same reason every other unrunnable check
        # in this file is — a green row here would be describing a request that never happened.
        rows.append((stray_target, "not attempted: the request got no answer"))
    elif session_cookie(headers) is not None and status != 200:
        rows.append((stray_target, (
            "it answered {} but still returned {}. The session is being established before "
            "the password is compared".format(status, SESSION_COOKIE))))
    else:
        rows.append((stray_target, None))

    body = json.dumps({"password": SMOKE_PASSWORD}).encode("utf-8")
    status, headers, payload, reason = http(base_url + "/api/login", "POST", body)
    if status is None:
        rows.append((right_target, "no answer at all: {}".format(reason)))
        rows.append((cookie_target, "not attempted: the login request got no answer"))
        rows.append((reuse_target, "not attempted: the login request got no answer"))
        rows.append((shape_target, "not attempted: the login request got no answer"))
        return rows
    if status != 200:
        rows.append((right_target, (
            "it answered {} for the very password this container was started with "
            "(AUTH_PASSWORD={!r}). Body: {!r}".format(status, SMOKE_PASSWORD, payload[:200]))))
        rows.append((cookie_target, "not attempted: the login was rejected"))
        rows.append((reuse_target, "not attempted: the login was rejected"))
        rows.append((shape_target, "not attempted: the login was rejected"))
        return rows
    rows.append((right_target, None))

    cookie = session_cookie(headers)
    if cookie is None:
        # This is the failure COOKIE_SECURE exists to prevent, and it is worth naming both
        # halves: over plain http a Secure cookie is issued by the server and dropped by the
        # client, so a gate that did not set COOKIE_SECURE=false would land here on a
        # perfectly healthy image and read like broken authentication.
        rows.append((cookie_target, (
            "the 200 carried no {} cookie. Either SessionMiddleware is no longer installed, "
            "or the response is Secure-only and this gate is talking plain http — it passes "
            "COOKIE_SECURE=false for exactly that reason, so a missing cookie here means the "
            "setting stopped being honoured".format(SESSION_COOKIE))))
        rows.append((reuse_target, "not attempted: there is no cookie to send"))
        rows.append((shape_target, "not attempted: there is no cookie to send"))
        return rows
    rows.append((cookie_target, None))

    status, _, payload, reason = http(base_url + "/api/config", cookie=cookie)
    if status is None:
        rows.append((reuse_target, "no answer at all: {}".format(reason)))
        rows.append((shape_target, "not attempted: the request got no answer"))
        return rows
    if status != 200:
        rows.append((reuse_target, (
            "it answered {}. The login succeeded and issued a cookie, but that cookie does "
            "not open a protected route: the session is not surviving the round trip — a "
            "changed signing key between request and response, a cookie the middleware "
            "cannot verify, or a `verify_auth` reading a session key the login handler never "
            "sets. Body: {!r}".format(status, payload[:200]))))
        rows.append((shape_target, "not attempted: the route did not answer 200"))
        return rows
    rows.append((reuse_target, None))

    try:
        config = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        rows.append((shape_target, "200 but the body is not JSON ({}): {!r}".format(
            error, payload[:200])))
        return rows
    if not isinstance(config, dict):
        rows.append((shape_target, "200 but the body is JSON and not an object: {!r}".format(
            config)))
        return rows
    # A fresh container mounts no volume and therefore has no data/config.json, so
    # `read_config()` returns its default document — which always carries `entities`. Checking
    # for the key rather than for the whole document keeps this from breaking the day somebody
    # adds a field, while still telling a config document apart from an error object.
    rows.append((shape_target, None if CONFIG_SHAPE_KEY in config else (
        "200 with a JSON object, but it has no {!r} key: {!r}. That is not the config "
        "document the frontend reads".format(CONFIG_SHAPE_KEY, sorted(config)[:10]))))
    return rows


def normalise_asset(href):
    """`./assets/index-abc.js` -> `/assets/index-abc.js`; absolute URLs are dropped.

    Vite is configured with `base: './'`, so everything in index.html arrives relative. An
    href pointing at another host is not this image's asset and downloading it would make the
    gate depend on somebody else's uptime, so it is left out here and the caller reports an
    empty list as a failure rather than as nothing to do.
    """
    if "://" in href or href.startswith("//"):
        return None
    while href.startswith("./"):
        href = href[2:]
    if not href.startswith("/"):
        href = "/" + href
    return href


def check_frontend(base_url, name):
    """(e) The built frontend is really in the image, and really served.

    The single biggest risk of this two-stage Dockerfile. Stage one runs `npm ci` and
    `npm run build` (which is `vue-tsc -b && vite build`); stage two copies `/app/dist` into
    `./static/`. If that build ever produced an empty or partial dist — a `COPY` that missed,
    a vite `outDir` change, a stage that failed in a way `docker build` did not notice — the
    image would still build, still start, and still pass every API check in this file, while
    serving a blank page to production.

    So: the HTML is fetched, the asset URLs are read out of it, and each one is downloaded and
    required to be non-empty and of a plausible content type. And separately, because
    StaticFiles is mounted with `html=True` and falls back to index.html for anything it
    cannot find, the file is looked for on disk from inside the container — a 200 on
    /assets/whatever is NOT evidence that the file exists.
    """
    rows = []
    html_target = "GET / answers 200 with HTML"
    links_target = "index.html references at least one built asset under /assets/"
    disk_target = "{} exists inside the image".format(INDEX_PATH)

    # The on-disk half first: it does not need the HTTP layer, so it still reports something
    # useful on a container that never came up.
    status, output = docker(
        ["exec", name, "python", "-c", STATIC_PROBE], EXEC_TIMEOUT)
    if status != 0:
        rows.append((disk_target, (
            "`docker exec` exited {} — the container is not running, or the image has no "
            "python to run it with. Output:\n{}".format(status, excerpt(output)))))
    else:
        try:
            probe = json.loads(output.strip().splitlines()[-1])
        except (IndexError, ValueError) as error:
            rows.append((disk_target, "the probe printed something unreadable ({}): {}".format(
                error, excerpt(output))))
        else:
            if not isinstance(probe, dict):
                # Cannot happen through the probe's own code path, so it means something else
                # wrote that line. Handled rather than left to raise, because an AttributeError
                # escaping here would take the whole gate down with a traceback instead of a
                # verdict — and lose every check that had not run yet.
                rows.append((disk_target, "the probe printed {!r}, not an object".format(probe)))
            elif not probe.get("index_exists"):
                rows.append((disk_target, (
                    "it does not. The frontend stage of the Dockerfile produced nothing that "
                    "reached the runtime image, so this container serves an API and no app "
                    "at all. {} contains: {!r}".format(STATIC_DIR, probe.get("entries")))))
            elif not probe.get("index_size"):
                rows.append((disk_target, "it exists and is 0 bytes"))
            else:
                rows.append(("{} ({} bytes)".format(disk_target, probe["index_size"]), None))

    if base_url is None:
        rows.append((html_target, "not attempted: the container never gave us an address"))
        rows.append((links_target, "not attempted: the container never gave us an address"))
        return rows

    status, headers, body, reason = http(base_url + "/")
    if status is None:
        rows.append((html_target, "no answer at all: {}".format(reason)))
        rows.append((links_target, "not attempted: / got no answer"))
        return rows
    if status != 200:
        rows.append((html_target, "it answered {}: {!r}".format(status, body[:200])))
        rows.append((links_target, "not attempted: / did not answer 200"))
        return rows
    media_type = content_type_of(headers)
    if media_type != "text/html":
        rows.append((html_target, (
            "it answered 200 with Content-Type {!r}. StaticFiles is mounted with html=True, "
            "so / should be index.html".format(media_type))))
        rows.append((links_target, "not attempted: / did not answer with HTML"))
        return rows
    rows.append((html_target, None))

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        rows.append((links_target, "index.html is not valid UTF-8: {}".format(error)))
        return rows

    hrefs = []
    for href in ASSET_PATTERN.findall(text):
        normalised = normalise_asset(href)
        if normalised is not None and normalised not in hrefs:
            hrefs.append(normalised)
    # `/assets/*` is where vite puts the hashed entry chunk and the stylesheet. Requiring at
    # least one of them, rather than any .js at all, is what makes this check about the BUILD:
    # a hand-written index.html with a `<script src="/main.js">` would satisfy a looser rule
    # while proving the bundler never ran.
    built = [href for href in hrefs if href.startswith("/assets/")]
    if not built:
        rows.append((links_target, (
            "it references none. The page came back as HTML, so something is being served — "
            "but nothing in it points at a built bundle, which is what an index.html copied "
            "from the repo root instead of from a vite build looks like. All .js/.css links "
            "found: {!r}".format(hrefs))))
        return rows
    rows.append(("{} ({})".format(links_target, ", ".join(built)), None))

    # Only the JS entry chunk is REQUIRED to exist, not a stylesheet: a build that inlined its
    # CSS would still be a working app, while a Vue SPA without its entry chunk cannot be one.
    # Whatever is actually referenced is downloaded, so a stylesheet that is there gets checked
    # like everything else.
    if not any(href.endswith(".js") for href in built):
        rows.append(("index.html references a built .js entry chunk", (
            "it references only {!r}. Without its entry chunk the page renders an empty "
            "<div id=\"app\"> and nothing else".format(built))))
    else:
        rows.append(("index.html references a built .js entry chunk", None))

    for href in built[:MAX_ASSETS]:
        target = "GET {} answers 200, non-empty, with the right content type".format(href)
        status, headers, body, reason = http(base_url + href)
        if status is None:
            rows.append((target, "no answer at all: {}".format(reason)))
            continue
        if status != 200:
            rows.append((target, "it answered {}".format(status)))
            continue
        if not body:
            # Status alone would not catch it: a bundle truncated to zero bytes answers a
            # perfectly good 200 and the app ships blank.
            rows.append((target, "200 but the body is empty (0 bytes)"))
            continue
        suffix = ".css" if href.endswith(".css") else ".js"
        expected = CONTENT_TYPES[suffix]
        media_type = content_type_of(headers)
        if media_type not in expected:
            # text/html here is the specific failure worth naming: StaticFiles with html=True
            # answers a missing path with index.html, 200 and all, so the asset "exists" as far
            # as a status check is concerned while the browser gets a page where it asked for
            # a script.
            rows.append((target, (
                "200 with Content-Type {!r}, expected one of {}. A text/html answer here means "
                "the file is NOT in the image: StaticFiles(html=True) fell back to index.html "
                "and returned it with a 200".format(media_type, ", ".join(expected)))))
            continue
        rows.append(("{} ({} bytes, {})".format(target, len(body), media_type), None))
    return rows


def check_survives_broker(name):
    """(f) The app must still be up, and its logs must say why it is unbothered.

    Everything above only works because an unreachable broker is survivable: there is no MQTT
    in CI, `lifespan` starts `mqtt_listener_loop()` as a background task, and that loop catches
    everything and sleeps RECONNECT_DELAY before trying again. If that ever changed — the
    connection moved into startup, an exception type escaping the `except Exception` — the
    container would die, and every check above would fail at once with no line saying which of
    them was the real cause. This check is that line.
    """
    rows = []
    running_target = "the container is still running after every check above"
    status, output = docker(
        ["inspect", "--format", "{{.State.Running}} {{.State.ExitCode}}", name],
        INSPECT_TIMEOUT)
    if status != 0:
        rows.append((running_target, (
            "docker inspect exited {}: {}".format(status, excerpt(output)))))
    else:
        state = output.strip()
        rows.append((running_target, None if state.startswith("true") else (
            "docker reports `Running ExitCode` = {!r}. The MQTT broker this gate points the "
            "app at does not exist on purpose, and the app is supposed to log a warning and "
            "retry — a container that exited instead means a broker outage now takes the "
            "service down with it, in production, where the broker is a real host that can "
            "reboot".format(state))))

    marker_target = "the logs report the reconnect loop, not a crash (bounded at {} s)".format(
        RECONNECT_BUDGET)
    deadline = time.monotonic() + RECONNECT_BUDGET
    logs = ""
    log_status = None
    while True:
        log_status, logs = docker(["logs", name], LOGS_TIMEOUT)
        if log_status == 0 and RECONNECT_MARKER in logs:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(RECONNECT_PAUSE)

    if log_status != 0:
        rows.append((marker_target, "`docker logs` exited {}: {}".format(
            log_status, excerpt(logs))))
    elif RECONNECT_MARKER not in logs:
        rows.append((marker_target, (
            "{!r} never appeared in {} s. The container is up, so something is running — but "
            "the MQTT listener is not reporting the failure it must be having against "
            "{}, which means either the listener task is not being started at all or its "
            "failures are being swallowed silently. Logs:\n{}".format(
                RECONNECT_MARKER, RECONNECT_BUDGET, UNREACHABLE_MQTT_HOST, excerpt(logs)))))
    else:
        rows.append((marker_target, None))

    # A traceback in a container that is nonetheless up means something is escaping rather than
    # being handled — an unawaited task, an error uvicorn caught and printed. It is the one
    # check here that could redden on something benign, and that is the direction to be wrong
    # in: it costs one look at a log that is printed right above the verdict.
    trace_target = "the logs carry no traceback"
    if log_status != 0:
        rows.append((trace_target, "not attempted: `docker logs` did not succeed"))
    else:
        rows.append((trace_target, None if TRACEBACK_MARKER not in logs else (
            "they do. The container is running, so this is not the app refusing to start — it "
            "is an exception escaping something that should have handled it. Logs:\n{}".format(
                excerpt(logs)))))
    return rows, logs


def main():
    image = os.environ.get(IMAGE_ENV)
    if not image:
        print("{} is not set: this gate tests the image it is given and has no default, "
              "because a default would silently gate whichever image happened to be on the "
              "daemon".format(IMAGE_ENV))
        raise SystemExit(1)
    name = os.environ.get(NAME_ENV)
    if not name:
        # No default here either, and this one is worth spelling out because a default would
        # not fail — it would work, quietly and wrongly, in two ways at once.
        # First, the cleanup: the workflow's `if: always()` step removes `<name>` and
        # `<name>-guard`, and it builds those names from the SAME variable. A dropped or
        # misspelled `env:` entry would leave this script naming its containers after the
        # fallback while the cleanup step went looking for the run-id ones, found nothing, and
        # swallowed the miss in its `|| true` — the gate stays green and the leak is permanent.
        # Second, collisions: the runner runs one docker daemon for every repository in the
        # fleet, so a constant fallback means two concurrent runs pick the SAME name — and
        # remove_container() below would then delete the other run's live container out from
        # under it.
        print("{} is not set: this gate names every container it starts after it, and a "
              "default would both hide containers from the workflow's cleanup step and make "
              "two concurrent runs collide on one name".format(NAME_ENV))
        raise SystemExit(1)

    rows = []
    transcripts = []

    rows.extend(check_image_contract(image))

    guard_rows, guard_output = check_missing_env_guard(image, name + GUARD_SUFFIX)
    transcripts.append(("the image run with no environment at all", guard_output))
    rows.extend(guard_rows)

    try:
        start_rows, base_url, start_output = start_container(image, name)
        transcripts.append(("`docker run -d` of the image under test", start_output))
        rows.extend(start_rows)

        rows.extend(check_info(base_url))
        rows.extend(check_protected(base_url))
        rows.extend(check_login_chain(base_url))
        rows.extend(check_frontend(base_url, name))

        # Last on purpose: "the container is still up" is only worth anything AFTER everything
        # else has had its turn at it.
        survive_rows, logs = check_survives_broker(name)
        transcripts.append(("the container's own log", logs))
        rows.extend(survive_rows)
    finally:
        # The workflow removes this container again under `if: always()`, which covers the case
        # where this whole script is killed by the step timeout and never gets here.
        remove_container(name)

    # The transcripts first, the verdicts last: in a CI log the verdicts are what somebody
    # scrolls to the bottom for, and the container's own output is what turns a one-line
    # verdict into a diagnosis.
    for label, text in transcripts:
        print("")
        print("--- {} ---".format(label))
        print(excerpt(text).rstrip() or "(no output)")
    print("")
    print("--- results ---")

    failures = []
    for target, reason in rows:
        if reason is None:
            print("ok   {}".format(target))
        else:
            print("FAIL {} -> {}".format(target, reason))
            failures.append(target)

    if failures:
        print("")
        print("smoke FAILED: {}/{} targets broken:".format(len(failures), len(rows)))
        for target in failures:
            print("  - {}".format(target))
        raise SystemExit(1)

    print("")
    print("smoke ok: {}/{} targets".format(len(rows), len(rows)))


if __name__ == "__main__":
    main()
