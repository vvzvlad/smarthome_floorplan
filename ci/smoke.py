"""Smoke gate for the smarthome_floorplan image, run on the CI runner against an
already-built image.

It is split in two, and the split is the thing to understand before changing anything here.

The OUTER half is this file: a plain `python3 ci/smoke.py` on the runner that drives `docker`
against the tag it is given in $SMOKE_IMAGE. It answers the questions that are about the
container as an object — how the image behaves with no environment at all, what
`docker inspect` says its CMD and WORKDIR are, whether the container is still alive when
everything else is done, and what it wrote to its log. None of those can be answered from a
process already running inside it.

The INNER half is the PROBE below: a program that lives here as a string constant and is fed
to `docker exec -i <name> python -u -`. It answers everything that is about HTTP, and it has
to run inside for a reason that cost this repo one red CI run to learn: **this job and the
docker daemon are not in the same network namespace.** Gitea's act_runner executes the job
inside its own job container, while the `docker` CLI it provides drives a daemon that lives
outside that container. So `-p 127.0.0.1::8000` publishes the port where THAT daemon runs,
`docker port` truthfully reports the port it bound there — and a
`urlopen("http://127.0.0.1:32768")` from this script reaches the JOB container's own loopback,
where nothing is listening. Every HTTP check came back `Connection refused` against a container
that was up, healthy and serving. The same reasoning already applied to the workspace, which is
why the test jobs stream it in as a tar over stdin instead of bind-mounting it; it applies to
ports too, and now it is written down in both places.

So: no port is published, no address is discovered, and nothing here assumes anything about
the network between the runner and the daemon. The probe talks to 127.0.0.1:8000 from inside
the container, where uvicorn is actually listening. `docker exec -i <name> python -u -` is the
mechanism the fleet already uses (token_checker's gate is piped in the same way), `-i` attaches
stdin without asking for a tty, and `docker exec` propagates the command's exit status, which
is what lets the outer half tell "the probe reported failures" from "the probe died".

The runner's job image (`docker.gitea.com/runner-images:ubuntu-latest`) ships /usr/bin/python3;
note that it ships `python3` and NOT a bare `python`, which is why both workflows invoke this
as `python3 ci/smoke.py`. Nothing beyond the standard library is imported on either side —
inside the container that is not even a choice, since the runtime image installs only the six
wheels in server/requirements.txt.

What this gate can be, and what it cannot
-----------------------------------------
There IS a test suite in this repo — 198 pytest cases for the backend and a vitest suite for
the frontend — and both run in their own jobs before the image is built. That makes this gate's
job narrower and sharper than "does the code work": the tests already answer that, in a
checkout, against source files. What they cannot answer is whether the ARTEFACT that gets
deployed carries that code, is wired up the way the deployment expects, and comes up on its
own. Every check below is one of those, and every one of them is a way this image has a
realistic chance of shipping broken while all 198 tests stay green:

* (a) the required-variable guard still fires. `server/src/settings.py` declares
  `auth_password` and `mqtt_host` with no default, so `Settings()` raises a pydantic
  ValidationError at IMPORT time and the container cannot start. That is the intended behaviour
  and it must stay intended: a deployment redeployed without AUTH_PASSWORD has to die loudly
  rather than come up with an empty password. `restart: always` in the compose file means it
  will be restarted either way, so the exit code and that message are the only difference
  between "somebody dropped a variable out of the stack" and a service that is quietly wide
  open. Outer half — it needs `docker run`.
* (b) the image comes up and serves /api/info, with the APP_TITLE the container was actually
  given. Checking that "something answered 200" would pass on a stale image, on a wrong image,
  and on an image whose settings never reached the app. Probe.
* (c) every authenticated endpoint still answers 401 without a session. The deployed service
  is reachable from the public internet, so a `Depends(verify_auth)` dropped from a route
  handler is the most expensive regression this repo can ship, and it is invisible in every
  other check here: the route would answer 200 and everything would look better than before.
  Probe.
* (d) the whole login chain works end to end: wrong password rejected with no cookie, right
  password accepted, session cookie issued, and that cookie actually opening a protected route
  — driven through `http.cookiejar`, so the cookie has to be acceptable to a client that
  obeys its attributes and not merely present in a header. Probe.
* (e) the frontend is really in there. This is the single biggest risk of a two-stage
  Dockerfile: stage one runs `npm ci && npm run build`, stage two copies `/app/dist` into
  `./static/`, and if that build ever produces an empty or partial `dist` the image still
  builds, still starts, still answers every API call above — and serves a blank page. The probe
  fetches the HTML, reads the asset URLs out of it and downloads each one: a missing file
  answers 404 (StaticFiles returns its own JSON 404 on a miss — the `html=True` index fallback
  applies to DIRECTORIES, not to arbitrary paths, and there is no 404.html in the build), so
  the status alone catches an absent bundle and the content type catches one that is being
  served as the wrong thing. The outer half looks for index.html on disk besides, which is a
  source of truth independent of the HTTP layer and the only place its SIZE is checked.
* (f) the app survives an unreachable broker. The whole gate rests on this: there is no MQTT
  broker in CI, and `mqtt_listener_loop()` is started as a background task by the lifespan
  handler, so the app is supposed to come up regardless and retry in a loop. If that ever
  stopped being true the container would die and everything above would go red at once with no
  line saying which failure was the real one. Outer half — the container's state and its log.
* (g) the image's declared contract: CMD, WORKDIR, and the absence of an ENTRYPOINT. Every
  `docker run` in this file, and production itself, depends on the image's own command being
  the thing that runs. Outer half.

Nothing here holds a credential or reaches an external service. The password is invented by
this file and passed in as AUTH_PASSWORD, the MQTT host points at a `.invalid` name, which RFC
2606 reserves so no resolver can ever answer it, and no port is exposed to anything. A gate
that needed the deployment's real password could not run on a pull request at all, and one
that reddened on somebody else's outage is a gate everybody learns to ignore.

Two properties matter and are easy to lose, so they are stated where they can be checked:

* Failures leave through SystemExit, never `assert` — on both sides of the split. Asserts
  vanish under PYTHONOPTIMIZE=1, which would silently turn this gate permanently green.
* Every check runs before anything is reported, so one run shows the full extent of the
  breakage instead of only the first broken thing. A check that CANNOT run reports itself as
  FAILED; it is never quietly skipped, which is the classic way a gate keeps reporting success
  while proving less and less. The probe's own report lines are parsed back into this gate's
  report, so a failure inside the container is one row in the same list as a failure outside
  it.
"""

import json
import os
import subprocess
import time

# The tag to test. Required rather than defaulted: a default would let a mistyped `env:` block
# in a workflow silently gate some other image that happens to be on the daemon.
IMAGE_ENV = "SMOKE_IMAGE"
# Base name for every container this gate starts. The workflows put the run id in it, because
# the runner has a single docker daemon shared by every repository in the fleet and two
# concurrent runs must not collide on a name.
# Required, exactly like the tag above, and for two reasons that both end in silence rather
# than in an error — see the message in main() where it is enforced.
NAME_ENV = "SMOKE_NAME"

# The short-lived guard container is named too, not left to docker's random name generator, and
# the reason is the one case that matters: `--rm` fires when a container EXITS, and a container
# that hangs never does. `subprocess` hitting its timeout kills the docker CLIENT on the
# runner; the container it started stays behind on the shared daemon. With no name nobody could
# ever remove it — not remove_container() here, not the workflow's `if: always()` step, because
# neither would know what to remove — and it would go on pinning the image, so the
# `docker rmi` at the end of the job would fail too, be swallowed by its `|| true`, and leave
# both a container and a few hundred MB of image on the daemon the whole fleet shares.
# Kept in step with the suffix list in both workflows' cleanup steps: if you move one, move the
# other.
GUARD_SUFFIX = "-guard"

# The Dockerfile's WORKDIR, its CMD, and where the built frontend lands. Hardcoded rather than
# read back out of the image: these are the contract between this repo and its image, so a
# Dockerfile that quietly moves them has to go red here and be looked at, not be politely
# followed.
APP_DIR = "/app"
EXPECTED_CMD = ["python", "main.py"]
STATIC_DIR = "/app/static"
INDEX_PATH = "/app/static/index.html"

# The two variables `Settings` declares without a default, spelled exactly as pydantic reports
# them: it prints FIELD names, which are lowercase, not the SCREAMING_CASE of the environment.
# Check (a) requires both to be named, one row each, so a guard that lost one of them cannot
# hide behind the other still firing.
REQUIRED_FIELDS = ["auth_password", "mqtt_host"]

# The environment the long-lived container runs with. Every value is invented here:
#   * AUTH_PASSWORD is what the probe logs in with, so the gate needs no real credential and can
#     run on a pull request. The probe reads it back out of its own environment rather than
#     carrying a second copy — see the note above the PROBE constant;
#   * MQTT_HOST points at a `.invalid` name, reserved by RFC 2606, so DNS cannot resolve it and
#     the container cannot reach a real broker even by accident. That is what makes check (f)
#     decidable rather than dependent on whether some broker happens to be reachable;
#   * COOKIE_SECURE=false because `cookie_secure` defaults to True, and `http.cookiejar` — like
#     a browser — refuses to SEND a Secure cookie over http. Without it the login chain would
#     break on a perfectly healthy image, in a way that reads like broken authentication;
#   * APP_TITLE is deliberately NOT the default "Z2M Floorplan": the probe reads it back out of
#     /api/info, and a value equal to the default would prove nothing at all, since the response
#     would be identical whether the variable arrived or was silently dropped. The probe
#     refuses to run that check against the default value, so this cannot decay unnoticed.
SMOKE_PASSWORD = "smoke-not-a-real-password"
UNREACHABLE_MQTT_HOST = "mqtt.smoke.invalid"
SMOKE_TITLE = "smoke-app-title-4f2a"

# The stable half of the line `mqtt_listener_loop()` logs when a connection attempt fails:
#   logger.warning("MQTT connection lost: %s. Reconnecting in %ss...", e, RECONNECT_DELAY)
# Matched on the phrase rather than on the whole sentence, because the exception text in the
# middle is aiomqtt's and changes with its version, while "Reconnecting in" is this repo's own
# wording and is the thing that has to keep being true.
RECONNECT_MARKER = "Reconnecting in"

# The first line of a python traceback. Its presence in the logs of a container that is
# nonetheless up means the reconnect loop is NOT what is happening — something is escaping and
# being printed by asyncio or uvicorn — and check (f) would otherwise pass on it, since the
# container really is running. This is the one check here that can go red on something
# harmless; that is the direction to be wrong in, and it is cheap to look at.
TRACEBACK_MARKER = "Traceback (most recent call last)"

# Printed by the probe on its last line and nowhere else. DECLARED TWICE — here and again
# inside the PROBE text — and the two have to keep agreeing. The duplication is deliberate:
# interpolating it into the probe would mean `.format()` on a body full of format calls of its
# own, or `%`-substitution, which would quietly turn the probe into a template that no longer
# runs as-is — and being able to paste that block into a container by hand and have it work is
# most of why it is a plain string. A drift costs a false RED (the outer half reports a probe
# that never finished), never a false green.
PROBE_MARKER = "smarthome_floorplan smoke probe ok"

# The prefix put in front of every row the probe reported, so the merged report says where each
# verdict was decided. Without it a reader of 30 result lines cannot tell which of them were
# taken from inside the container and which from the runner, and that distinction is exactly
# what the failure this file was rewritten for turned on.
PROBE_ROW_PREFIX = "[in-container] "

# Bounds. Every docker call gets one, because a gate that hangs is worse than a gate that
# fails: it holds a slot on a runner the whole fleet queues for until the step timeout kills it,
# and a killed step never runs its cleanup.
# The numbers are generous against the real cost — this image starts and answers in a couple of
# seconds — and are sized for a shared runner under load right after a build. Their worst-case
# SUM is what the smoke step's `timeout-minutes` in both workflows has to exceed, so it is
# spelled out here, in the order the calls actually happen:
#   30 (inspect config) + 30 (rm guard) + 90 (guard run) + 30 (rm main) + 60 (run -d)
#   + 210 (docker exec: the HTTP probe) + 60 (docker exec: the static file on disk)
#   + 30 (inspect state) + 45 (reconnect poll: 30 budget + one 15 s `docker logs` in flight)
#   + 30 (rm main, in the finally)
#   = 615 s, a little over 10 minutes. Both workflows allow 12.
# PROBE_TIMEOUT is the one number here that is not arbitrary: the probe documents its OWN
# worst case as ~150 s (a 65 s readiness poll, then 15 HTTP requests bounded at 5 s each), so
# 210 leaves it a full minute of headroom for a slow `docker exec` on a loaded daemon while
# still fitting the sum above inside the step timeout.
# Two of these `rm`s are pre-run cleanups: every container this gate starts is removed by name
# before it is started, so a re-run from the UI — which keeps the same run id, hence the same
# $SMOKE_NAME — cannot die on "name already in use".
INSPECT_TIMEOUT = 30
REMOVE_TIMEOUT = 30
GUARD_TIMEOUT = 90
START_TIMEOUT = 60
PROBE_TIMEOUT = 210
EXEC_TIMEOUT = 60
LOGS_TIMEOUT = 15

# The reconnect-marker poll, bounded in WALL CLOCK rather than in attempts: each attempt shells
# out to `docker logs`, whose own timeout is 15 s, so an attempt-counted bound would multiply
# into minutes the moment the daemon got slow. The first warning is logged as soon as the first
# connection attempt fails, and with an unresolvable host that is a DNS failure rather than a
# connect timeout, so it arrives within a second; RECONNECT_DELAY in the app is 5 s, so 30 s
# covers several full turns of the loop.
RECONNECT_BUDGET = 30
RECONNECT_PAUSE = 0.5

# How much of an unexpected output reaches the log. Container logs can run to thousands of lines
# when something loops, and an unbounded dump would bury the verdict.
EXCERPT_CHARS = 4000

# Run inside the container with `docker exec`, to answer the one question about the filesystem
# that HTTP cannot: is the built frontend actually on disk where the app serves it from. The
# probe's own asset checks would already catch a missing bundle — StaticFiles answers a miss
# with its own 404 — so this is not the only line of defence and is not pretending to be. What
# it adds is a source of truth that does not go through the HTTP layer at all (it still says
# something useful when uvicorn never came up), and the file's SIZE, which no request for `/`
# can report. Printed as one JSON line so a failure carries the directory listing that explains
# it.
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


# The program fed to `python -u -` inside the container under test. It lives here as a string
# rather than as a second file so that this gate stays one artifact: the workflows already pass
# it nothing but an image tag and a container name, and a second file is a second thing to
# forget to copy when this repo's CI is cloned into the next one.
#
# `-u` is not decoration: this stdout is a pipe, and CPython block-buffers those. A normal exit
# flushes (SystemExit included, so a self-reported failure is never lost), but a probe killed by
# PROBE_TIMEOUT would otherwise take every line it had already printed down with it — in exactly
# the run whose output is the only thing left to diagnose from.
#
# It takes NO parameters. Everything it needs is already in the container's environment, because
# `docker exec` runs with the environment the container was created with: AUTH_PASSWORD and
# APP_TITLE are the very values the outer half passed to `docker run`, so the probe compares
# what the app ANSWERS against what the container was actually GIVEN, rather than against a
# second copy of a constant that could drift from it. The only thing declared on both sides is
# PROBE_MARKER, and the note on it above explains why that one is copied rather than
# interpolated.
PROBE = r'''
"""Runs INSIDE a container of the smarthome_floorplan image, fed to `python -u -` over stdin.

It talks to 127.0.0.1:8000 — the address uvicorn actually binds, in the only network namespace
where that address means the application. Nothing is published to any host, and nothing here
needs to know how the runner and the docker daemon are connected, which is precisely the
assumption that broke the previous version of this gate.

It is pure stdlib, which inside this image is not a preference but a fact: the runtime stage
installs fastapi, uvicorn, aiomqtt, python-multipart, itsdangerous and pydantic-settings, and
nothing else. urllib, http.cookiejar, json and re are all there.

The cookie handling goes through http.cookiejar rather than through hand-copied headers, and
that is a real check rather than a convenience: a cookiejar applies the cookie's own attributes,
so a Secure cookie would be stored and then NOT sent back over http — exactly as a browser
would refuse it. The container is started with COOKIE_SECURE=false for that reason, and if that
setting ever stopped being honoured this is where it would show up.

Every target is checked before anything is reported, and a check that cannot run reports itself
as FAILED rather than being skipped. Failures leave through SystemExit, never `assert`.
"""

import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.request

# uvicorn binds 0.0.0.0:${PORT:-8000} and the gate deliberately does not set PORT, so this
# exercises the same default the Dockerfile, the compose file and the Traefik service port all
# assume. 127.0.0.1 rather than the container's external address: this runs inside, and
# loopback is the one address that cannot be wrong.
BASE_URL = "http://127.0.0.1:8000"

# Printed on the last line and nowhere else. This is the outer half's PROBE_MARKER, written out
# again because this text is handed to another interpreter and cannot import anything from the
# file it lives in. If you move one, move the other; the note there explains why a drift costs
# a false red rather than a false green.
PROBE_MARKER = "smarthome_floorplan smoke probe ok"

# The default `app_title` in server/src/settings.py. The APP_TITLE check below refuses to run
# against this value: comparing the app's answer to the default would pass whether the variable
# reached the application or was silently dropped, which is a check that proves nothing while
# printing an `ok`.
DEFAULT_APP_TITLE = "Z2M Floorplan"

# The cookie SessionMiddleware is configured with in server/src/api.py. A rename of it should be
# a finding rather than a silent pass, which is why it is named here rather than "whatever
# cookie came back".
SESSION_COOKIE = "fp_session"

# Every route that carries `Depends(verify_auth)` and is reachable with a plain GET. The write
# routes behind the same dependency are deliberately absent: `/api/config` and `/api/icon` have
# POST (and, for the icon, DELETE) halves, `/api/mqtt/publish` and `/api/entity/{id}/command`
# are POST-only with no GET at all. Probing any of them unauthenticated would only prove the
# same 401 that the reads below prove, while a bug in this file would then be issuing writes
# against a container. Note that `/api/mqtt/topics` is not the read half of
# `/api/mqtt/publish` — they are two different routes; it is listed here on its own merits, as
# the GET that exposes every value seen on the configured MQTT topics.
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

# Read out of index.html: `src="..."` and `href="..."` ending in .js or .css. Vite is configured
# with `base: './'`, so they arrive as `./assets/index-<hash>.js` and are normalised below.
ASSET_PATTERN = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+\.(?:js|css))["']""", re.I)

# The content types a working build can legitimately serve for each kind of asset. A SET rather
# than one exact string on purpose: Starlette derives these from python's `mimetypes`, whose
# answer for `.js` has changed across releases (application/javascript -> text/javascript), and
# a base-image bump is not a reason to redden this gate. What IS a finding is a stylesheet
# served as text/html — which is exactly what the SPA fallback does when the file is missing.
CONTENT_TYPES = {
    ".js": ("text/javascript", "application/javascript", "application/x-javascript"),
    ".css": ("text/css",),
}

# How many assets are downloaded. A working build emits two or three; the cap exists so a
# generated index.html that somehow referenced a hundred files could not turn this probe into a
# long download loop, and it is what the timeout arithmetic in the outer half is computed
# against.
MAX_ASSETS = 8

# The readiness poll, bounded in WALL CLOCK rather than in attempts: each attempt is an HTTP
# request with its own 5 s timeout, so an attempt-counted bound would multiply into minutes the
# moment the container got slow. 60 s is roughly twenty times what this app needs — uvicorn is
# listening within a second or two of the interpreter starting — and the 0.5 s pause keeps a
# fast container from waiting on us.
# The whole probe's worst case follows from these: 65 s here (the budget plus one request in
# flight), then at most 15 further requests at 5 s each — about 150 s, which is the number the
# outer half's PROBE_TIMEOUT is set against.
READY_BUDGET = 60
READY_PAUSE = 0.5
HTTP_TIMEOUT = 5

# How much of an unexpected body reaches the log. A container that is not this application can
# answer with an HTML error page, and an unbounded dump of it would bury the verdict.
EXCERPT_BYTES = 200


def describe(error):
    return "{}: {}".format(type(error).__name__, error)


def opener_with_jar():
    """A client that keeps cookies, and the jar it keeps them in."""
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def fetch(opener, path, method="GET", body=None):
    """One request. Returns (status, headers, body_bytes, reason).

    A 4xx or a 5xx is an ANSWER here, not an error: `verify_auth` returning 401 is the single
    most important thing this gate checks, so an HTTPError is unwrapped into a status like any
    other rather than being raised. `reason` is set only when there was no answer at all —
    connection refused, timeout, a half-closed socket — and the status is then None.

    Nothing here asks for compression, and that is what keeps the bodies readable: urllib sends
    `Accept-Encoding: identity`, so GZipMiddleware — which honours the header and would
    otherwise compress the ~46 KB config payload — leaves every body below untouched. Adding a
    gzip to that header would silently turn each body comparison into a comparison against
    compressed bytes.
    """
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT) as response:
            return response.status, response.headers, response.read(), None
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read(), None
    except Exception as error:
        return None, None, b"", describe(error)


def header_cookie(headers):
    """The `fp_session=...` pair out of a response's Set-Cookie headers, or None.

    Read from the RAW header rather than from the jar, and only used where the question is
    whether the server tried to set a session at all. The jar is the right instrument for "can a
    client use this cookie"; it is the wrong one for "was one issued", because a jar that
    rejected the cookie on its own rules looks exactly like a server that never sent it.
    """
    if headers is None:
        return None
    for value in headers.get_all("Set-Cookie") or []:
        pair = value.split(";", 1)[0].strip()
        if pair.startswith(SESSION_COOKIE + "="):
            return pair
    return None


def jar_has_session(jar):
    return any(cookie.name == SESSION_COOKIE for cookie in jar)


def content_type_of(headers):
    """The bare media type, without the `; charset=utf-8` a text response carries."""
    if headers is None:
        return ""
    return (headers.get("Content-Type") or "").split(";")[0].strip().lower()


def normalise_asset(href):
    """`./assets/index-abc.js` -> `/assets/index-abc.js`; absolute URLs are dropped.

    An href pointing at another host is not this image's asset and downloading it would make the
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


def check_info(anonymous):
    """(b) Wait for /api/info, then require it to carry the APP_TITLE the container was given."""
    rows = []
    ready_target = "GET /api/info answers 200 (bounded at {} s)".format(READY_BUDGET)
    title_target = "/api/info reports the APP_TITLE this container was started with"

    deadline = time.monotonic() + READY_BUDGET
    status = None
    body = b""
    reason = "no attempt was made"
    while True:
        status, _, body, reason = fetch(anonymous, "/api/info")
        if status == 200:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(READY_PAUSE)

    if status != 200:
        # The LAST reason is reported, not the first: the first is almost always "connection
        # refused" from the moment before uvicorn had bound, which describes nothing. The last
        # one is the state the endpoint was still in when the budget ran out.
        rows.append((ready_target, (
            "it never did in {} s. Last answer: status {}, {}. This probe runs INSIDE the "
            "container, so the address cannot be wrong and nothing about the runner's network "
            "is involved: uvicorn is not listening on 8000, or the app failed to import after "
            "the interpreter started".format(
                READY_BUDGET, status, reason or "no transport error"))))
        rows.append((title_target, "not attempted: /api/info never answered 200"))
        return rows
    rows.append((ready_target, None))

    expected = os.environ.get("APP_TITLE")
    if not expected:
        rows.append((title_target, (
            "APP_TITLE is not set in this container's environment, so there is nothing to "
            "compare against. The gate is supposed to pass a non-default title precisely so "
            "this check can prove the environment reaches the application")))
        return rows
    if expected == DEFAULT_APP_TITLE:
        # Refusing to run is the point. Comparing against the default would print an `ok` for a
        # container that never received the variable at all.
        rows.append((title_target, (
            "APP_TITLE is {!r}, which is the application's own default — this check would pass "
            "whether the variable reached the app or was dropped, so it proves nothing and is "
            "reported as broken rather than green".format(expected))))
        return rows

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        rows.append((title_target, "200 but the body is not JSON ({}): {!r}".format(
            error, body[:EXCERPT_BYTES])))
        return rows
    if not isinstance(payload, dict):
        rows.append((title_target, "200 but the body is JSON and not an object: {!r}".format(
            payload)))
        return rows
    rows.append(("{} ({!r})".format(title_target, expected),
                 None if payload.get("title") == expected else (
                     "it reports {!r} instead. Either the environment did not reach the "
                     "application — which would mean nothing else here is testing the "
                     "configuration it thinks it is — or /api/info stopped reading "
                     "settings.app_title".format(payload.get("title")))))
    return rows


def check_protected(anonymous):
    """(c) Every authenticated route must answer 401 without a session."""
    rows = []
    for path in PROTECTED_PATHS:
        target = "GET {} without a session answers 401".format(path)
        status, _, body, reason = fetch(anonymous, path)
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
                "deployed service is reachable from the public internet — a "
                "`Depends(verify_auth)` has been dropped from its handler. Body: {!r}".format(
                    body[:EXCERPT_BYTES]))))
            continue
        rows.append((target, (
            "it answered {}. Not a disclosure, but not the contract either: the frontend treats "
            "401 as 'show the login screen', and any other status leaves it stuck. "
            "Body: {!r}".format(status, body[:EXCERPT_BYTES]))))
    return rows


def check_login_chain():
    """(d) Wrong password rejected, right password accepted, and the cookie really opens a door.

    Deliberately end to end rather than three independent probes: what breaks in this area is
    the seam between the parts — SessionMiddleware signing a cookie the app cannot verify, a
    `secrets.compare_digest` comparing against the wrong thing, `verify_auth` reading a key the
    login handler never set. Each half looks fine on its own, and the pytest suite drives all of
    it through Starlette's TestClient, which never puts a cookie on the wire.

    The password comes from the container's own environment, so this logs in with exactly what
    the container was started with rather than with a second copy of a constant.
    """
    rows = []
    wrong_target = "POST /api/login with the wrong password answers 401"
    stray_target = "POST /api/login with the wrong password sets no session cookie"
    right_target = "POST /api/login with the right password answers 200"
    cookie_target = "...and the cookie jar accepts a {} cookie".format(SESSION_COOKIE)
    reuse_target = "GET /api/config with that cookie answers 200"
    shape_target = "...with a JSON object carrying {!r}".format(CONFIG_SHAPE_KEY)

    password = os.environ.get("AUTH_PASSWORD")
    if not password:
        for target in (wrong_target, stray_target, right_target, cookie_target, reuse_target,
                       shape_target):
            rows.append((target, (
                "AUTH_PASSWORD is not set in this container's environment. That should be "
                "impossible — the app cannot import without it — so something other than this "
                "image is running here")))
        return rows
    # Guaranteed to differ from the real one, and derived rather than declared so it cannot
    # accidentally BE the real one the day somebody changes the password the gate passes.
    wrong_password = password + "-wrong"

    opener, jar = opener_with_jar()
    body = json.dumps({"password": wrong_password}).encode("utf-8")
    status, headers, payload, reason = fetch(opener, "/api/login", "POST", body)
    if status is None:
        rows.append((wrong_target, "no answer at all: {}".format(reason)))
        rows.append((stray_target, "not attempted: the request got no answer"))
    else:
        if status == 200:
            # The worst outcome in this file after an open route: the password check is not
            # checking. A `compare_digest` against an empty `auth_password` would do exactly
            # this, and so would a handler that stopped comparing at all.
            rows.append((wrong_target, (
                "it answered 200 and issued a session. The password comparison is not "
                "rejecting anything, which makes every protected route above reachable by "
                "anyone who posts a login")))
        elif status != 401:
            rows.append((wrong_target, "it answered {}: {!r}".format(
                status, payload[:EXCERPT_BYTES])))
        else:
            rows.append((wrong_target, None))
        # Asked independently of the status above, deliberately. A wrong password must not
        # produce a session under ANY status — including the 200 that would already have failed
        # the previous row — and making this row conditional on the status would let the worst
        # case of all (accepted AND handed a session) report only one finding.
        # Both instruments, because they answer different questions: the jar says "a client
        # would now be carrying a session", the raw header says "the server tried to give it
        # one". A handler that establishes the session before comparing the password trips the
        # second one even if the jar happened to reject the cookie.
        issued = header_cookie(headers)
        if jar_has_session(jar) or issued is not None:
            rows.append((stray_target, (
                "it answered {} and returned a {} cookie. The session is being established "
                "before, or regardless of, the password comparison".format(
                    status, SESSION_COOKIE))))
        else:
            rows.append((stray_target, None))

    opener, jar = opener_with_jar()
    body = json.dumps({"password": password}).encode("utf-8")
    status, headers, payload, reason = fetch(opener, "/api/login", "POST", body)
    if status is None:
        rows.append((right_target, "no answer at all: {}".format(reason)))
        for target in (cookie_target, reuse_target, shape_target):
            rows.append((target, "not attempted: the login request got no answer"))
        return rows
    if status != 200:
        rows.append((right_target, (
            "it answered {} for the very password this container was started with. "
            "Body: {!r}".format(status, payload[:EXCERPT_BYTES]))))
        for target in (cookie_target, reuse_target, shape_target):
            rows.append((target, "not attempted: the login was rejected"))
        return rows
    rows.append((right_target, None))

    if not jar_has_session(jar):
        # This is the failure COOKIE_SECURE exists to prevent, and it is worth naming both
        # halves: over plain http a cookiejar stores a Secure cookie but will not send it back,
        # so a gate that did not pass COOKIE_SECURE=false would land here on a perfectly healthy
        # image and read like broken authentication.
        issued = header_cookie(headers)
        rows.append((cookie_target, (
            "the jar holds no {} cookie{}. Either SessionMiddleware is no longer installed, or "
            "the cookie came back Secure-only and this probe speaks plain http — the container "
            "is started with COOKIE_SECURE=false for exactly that reason, so this means the "
            "setting stopped being honoured".format(
                SESSION_COOKIE,
                " even though the response carried one" if issued else
                " and the response carried none"))))
        for target in (reuse_target, shape_target):
            rows.append((target, "not attempted: there is no usable cookie"))
        return rows
    rows.append((cookie_target, None))

    status, _, payload, reason = fetch(opener, "/api/config")
    if status is None:
        rows.append((reuse_target, "no answer at all: {}".format(reason)))
        rows.append((shape_target, "not attempted: the request got no answer"))
        return rows
    if status != 200:
        rows.append((reuse_target, (
            "it answered {}. The login succeeded and the jar carries a session cookie, but that "
            "cookie does not open a protected route: the session is not surviving the round "
            "trip — a signing key that differs between request and response, a cookie the "
            "middleware cannot verify, or a `verify_auth` reading a session key the login "
            "handler never sets. Body: {!r}".format(status, payload[:EXCERPT_BYTES]))))
        rows.append((shape_target, "not attempted: the route did not answer 200"))
        return rows
    rows.append((reuse_target, None))

    try:
        config = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        rows.append((shape_target, "200 but the body is not JSON ({}): {!r}".format(
            error, payload[:EXCERPT_BYTES])))
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
        "200 with a JSON object, but it has no {!r} key: {!r}. That is not the config document "
        "the frontend reads".format(CONFIG_SHAPE_KEY, sorted(config)[:10]))))
    return rows


def check_frontend(anonymous):
    """(e) The built frontend is really served.

    The single biggest risk of the two-stage Dockerfile. Stage one runs `npm ci` and
    `npm run build` (which is `vue-tsc -b && vite build`); stage two copies `/app/dist` into
    `./static/`. If that build ever produced an empty or partial dist the image would still
    build, still start, and still pass every API check above, while serving a blank page.

    A missing asset is caught by its status: StaticFiles answers a path it cannot find with its
    own JSON 404 — the `html=True` index fallback applies to DIRECTORIES, not to arbitrary
    paths, and the build ships no 404.html — so there is no SPA-style catch-all here to turn a
    missing bundle into a cheerful 200. The content-type check below is therefore not about
    that; it is about a file that IS served but as the wrong kind of thing, which is what a
    mangled build or a mis-typed extension looks like from a browser's point of view.
    """
    rows = []
    html_target = "GET / answers 200 with HTML"
    links_target = "index.html references at least one built asset under /assets/"
    chunk_target = "index.html references a built .js entry chunk"

    status, headers, body, reason = fetch(anonymous, "/")
    if status is None:
        rows.append((html_target, "no answer at all: {}".format(reason)))
        for target in (links_target, chunk_target):
            rows.append((target, "not attempted: / got no answer"))
        return rows
    if status != 200:
        rows.append((html_target, "it answered {}: {!r}".format(status, body[:EXCERPT_BYTES])))
        for target in (links_target, chunk_target):
            rows.append((target, "not attempted: / did not answer 200"))
        return rows
    media_type = content_type_of(headers)
    if media_type != "text/html":
        rows.append((html_target, (
            "it answered 200 with Content-Type {!r}. StaticFiles is mounted with html=True, so "
            "/ should be index.html".format(media_type))))
        for target in (links_target, chunk_target):
            rows.append((target, "not attempted: / did not answer with HTML"))
        return rows
    rows.append((html_target, None))

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        rows.append((links_target, "index.html is not valid UTF-8: {}".format(error)))
        rows.append((chunk_target, "not attempted: index.html could not be decoded"))
        return rows

    hrefs = []
    for href in ASSET_PATTERN.findall(text):
        normalised = normalise_asset(href)
        if normalised is not None and normalised not in hrefs:
            hrefs.append(normalised)
    # `/assets/*` is where vite puts the hashed entry chunk and the stylesheet. Requiring at
    # least one of them, rather than any .js at all, is what makes this check about the BUILD: a
    # hand-written index.html with a `<script src="/main.js">` would satisfy a looser rule while
    # proving the bundler never ran.
    built = [href for href in hrefs if href.startswith("/assets/")]
    if not built:
        rows.append((links_target, (
            "it references none. The page came back as HTML, so something is being served — but "
            "nothing in it points at a built bundle, which is what an index.html copied from "
            "the repo root instead of from a vite build looks like. All .js/.css links found: "
            "{!r}".format(hrefs))))
        rows.append((chunk_target, "not attempted: no built assets were referenced"))
        return rows
    rows.append(("{} ({})".format(links_target, ", ".join(built)), None))

    # Only the JS entry chunk is REQUIRED to exist, not a stylesheet: a build that inlined its
    # CSS would still be a working app, while a Vue SPA without its entry chunk cannot be one.
    # Whatever is actually referenced is downloaded, so a stylesheet that is there gets checked
    # like everything else.
    if not any(href.endswith(".js") for href in built):
        rows.append((chunk_target, (
            "it references only {!r}. Without its entry chunk the page renders an empty "
            "<div id=\"app\"> and nothing else".format(built))))
    else:
        rows.append((chunk_target, None))

    for href in built[:MAX_ASSETS]:
        target = "GET {} answers 200, non-empty, with the right content type".format(href)
        status, headers, body, reason = fetch(anonymous, href)
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
            # Not a missing file — that answers 404 and was handled above. This is a file that
            # IS there and is being served as the wrong kind of thing, which a browser refuses
            # to execute or apply while the server reports a perfectly good 200.
            rows.append((target, (
                "200 with Content-Type {!r}, expected one of {}. The file exists — a missing "
                "one would have answered 404 — so it is being served under the wrong media "
                "type, and a browser will decline to use it".format(
                    media_type, ", ".join(expected)))))
            continue
        rows.append(("{} ({} bytes, {})".format(target, len(body), media_type), None))
    return rows


def main():
    # A client with NO cookie jar, used for everything that must be unauthenticated. Keeping it
    # separate from the login chain's openers is what makes the 401 checks mean something: a
    # single shared client would carry a session from an earlier check into a later one, and
    # every protected route would answer 200 for entirely the right reason.
    anonymous = urllib.request.build_opener()

    rows = []
    rows.extend(check_info(anonymous))
    rows.extend(check_protected(anonymous))
    rows.extend(check_login_chain())
    rows.extend(check_frontend(anonymous))

    failures = []
    for target, reason in rows:
        if reason is None:
            print("ok   {}".format(target))
        else:
            print("FAIL {} -> {}".format(target, reason))
            failures.append(target)

    if failures:
        print("probe FAILED: {}/{} targets broken".format(len(failures), len(rows)))
        raise SystemExit(1)

    print("{}: {}/{} targets".format(PROBE_MARKER, len(rows), len(rows)))


if __name__ == "__main__":
    main()
'''


def excerpt(text):
    """Bound what reaches the log, and say so when something was cut."""
    if text is None:
        return ""
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[:EXCERPT_CHARS] + "\n[... truncated at {} characters]".format(EXCERPT_CHARS)


def docker(args, timeout, stdin_text=None):
    """Run a docker command.

    Returns (status, output) with stderr folded into stdout, because everything here is read by
    a human out of a CI log where the interleaving is the useful part. A status of None means
    the command produced no exit code at all — it timed out, or docker is not there — and
    `output` then explains which.
    """
    argv = ["docker"] + args
    try:
        completed = subprocess.run(
            argv,
            input=stdin_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True)
    except FileNotFoundError:
        return None, (
            "`docker` is not on PATH. This gate drives the daemon from the runner, so it cannot "
            "run anywhere the docker CLI is missing")
    except subprocess.TimeoutExpired as error:
        return None, "`{}` did not finish within {} s. Output so far:\n{}".format(
            " ".join(argv), timeout, excerpt(error.output))
    return completed.returncode, completed.stdout or ""


def remove_container(name):
    """Best effort. Never the reason a check fails; the workflow cleans up too."""
    docker(["rm", "-f", name], REMOVE_TIMEOUT)


def check_image_contract(image):
    """(g) What the image DECLARES: its command, where it runs, and that nothing wraps them."""
    rows = []
    target = "docker inspect {}".format(image)
    status, output = docker(
        ["inspect", "--format", "{{json .Config}}", image], INSPECT_TIMEOUT)
    if status is None:
        # No exit code at all: the docker CLI is missing or the call ran out its timeout. The
        # message from docker() already says which, and neither of them means what a non-zero
        # exit means, so they must not share its wording.
        rows.append((target, output))
        return rows
    if status != 0:
        rows.append((target, (
            "it exited {} — the tag does not exist on this daemon, so the build step and this "
            "step disagree about what was built. Output:\n{}".format(status, excerpt(output)))))
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
            "it is {!r}. Every container this gate starts runs the image's own command, and so "
            "does production — a silent change here means the checks below and the deployment "
            "are describing two different programs".format(cmd))))

    # An ENTRYPOINT would prepend itself to the CMD above, so `docker run <image>` would no
    # longer be `python main.py` and check (a)'s verdict would be about something else entirely.
    # There is none today, and this is what keeps it that way.
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
            "it is {!r}. The CMD is the relative path {!r}, which resolves against it, and so "
            "do `config_path` and `icon_path` — both are declared relative (data/config.json, "
            "data/icon.png), which is what makes them land inside the mounted volume. Move the "
            "working directory and the app either fails to start or quietly keeps its state "
            "somewhere that is not the volume. (`static/` is NOT in this list: api.py resolves "
            "it against its own __file__, so it follows the code rather than the cwd.)".format(
                working_dir, EXPECTED_CMD[1]))))

    return rows


def check_missing_env_guard(image, name):
    """(a) Run the image with NO environment at all: it must die, and name both variables.

    This is one of the checks that cannot live inside a container, and the one that most
    directly describes a real deployment failure — the stack redeployed without AUTH_PASSWORD.
    The mechanism is `Settings()` at the bottom of server/src/settings.py: it runs at import
    time, `auth_password` and `mqtt_host` have no defaults, so pydantic raises a ValidationError
    before uvicorn is ever reached.

    That it fires at all depends on the image carrying no `.env` file — `SettingsConfigDict`
    names one — and it does not: the Dockerfile's final stage copies only requirements.txt,
    main.py, src/ and the built frontend, and `.dockerignore` lists `.env` besides. A future
    Dockerfile that copied the repo root wholesale would break this guard in production without
    breaking a single test, and this check is what would notice.

    The image's own CMD is kept — no `-e`, no override. That is safe to run to completion here
    precisely because the guard makes it terminate on its own; there is no restart loop inside
    this image to hang on.

    `--rm` AND a name: the flag covers the container that exits, the name covers the one that
    does not. See GUARD_SUFFIX above for why the second half is not redundant.
    """
    rows = []
    target = "`docker run --rm {}` with no environment at all".format(image)
    # A re-run from the UI reuses the run id, so it reuses this name too, and a previous attempt
    # killed by the step timeout may have left the container behind. A no-op when it did not.
    remove_container(name)
    status, output = docker(["run", "--rm", "--name", name, image], GUARD_TIMEOUT)
    if status is None:
        rows.append((target, output))
        return rows, output
    if status == 0:
        rows.append((target, (
            "it exited 0. The required-variable guard did not fire, so a stack redeployed "
            "without AUTH_PASSWORD would come up looking perfectly healthy — with an app whose "
            "login endpoint compares against whatever `auth_password` ended up being. "
            "Output:\n{}".format(excerpt(output)))))
        return rows, output
    rows.append(("{} exits non-zero (got {})".format(target, status), None))

    # A non-zero exit on its own is NOT enough, and this is the whole reason the output is
    # matched too: a typo in an import, a syntax error, a missing wheel — all of them exit
    # non-zero, and all of them would make this check pass while proving nothing about the
    # guard. Pydantic's ValidationError names the FIELDS it is missing, one per line, and those
    # names are the contract with the deployment.
    # One row per variable, not one row for both: a guard that lost `mqtt_host` (say, by someone
    # giving it a default "localhost") would still fire on `auth_password`, and a single
    # combined check would go on reporting success for a service that now silently points its
    # broker connection at itself.
    for field in REQUIRED_FIELDS:
        rows.append((
            "...and its output names the missing field {!r}".format(field),
            None if field in output else (
                "nothing in the output mentions it. The image exited {}, but either this is not "
                "the validation guard firing — it is the app dying of something else before it "
                "got there — or {!r} has quietly acquired a default and is no longer required "
                "at all. Output:\n{}".format(status, field, excerpt(output)))))
    return rows, output


def start_container(image, name):
    """Start the long-lived container everything else runs against.

    NO PORT IS PUBLISHED, and that is the correction this whole file was restructured around:
    the job runs inside act_runner's container while docker talks to the host's daemon, so a
    published port lands on the HOST's loopback and is unreachable from here. Nothing outside
    the container needs to reach the app — the probe runs inside it — so nothing is exposed at
    all, which as a bonus keeps the smoke container off every interface on the runner host for
    its lifetime.

    Started with the image's own CMD — no `--entrypoint`, which does not merely replace the
    entrypoint but also DROPS the image's CMD, making "does the image's own command bring the
    app up" unanswerable, and that is most of what the checks after this one are about.
    """
    rows = []
    target = "`docker run -d` starts a container of {}".format(image)
    remove_container(name)
    status, output = docker(
        [
            "run", "-d", "--name", name,
            "-e", "AUTH_PASSWORD=" + SMOKE_PASSWORD,
            "-e", "MQTT_HOST=" + UNREACHABLE_MQTT_HOST,
            "-e", "COOKIE_SECURE=false",
            "-e", "APP_TITLE=" + SMOKE_TITLE,
            image,
        ],
        START_TIMEOUT)
    if status is None:
        rows.append((target, output))
        return rows, False, output
    if status != 0:
        rows.append((target, "`docker run -d` exited {}:\n{}".format(status, excerpt(output))))
        return rows, False, output
    rows.append((target, None))
    return rows, True, output


def probe_report_rows(output):
    """Parse the probe's own report lines back into rows of this gate's report.

    The probe prints exactly the same `ok   <target>` / `FAIL <target> -> <reason>` shape this
    file does, so its verdicts can be merged into one list instead of arriving as a single
    opaque "the probe failed". That matters for the same reason the guard check has one row per
    variable: a run that breaks four routes should say four things.
    """
    rows = []
    for line in output.splitlines():
        if line.startswith("ok   "):
            rows.append((PROBE_ROW_PREFIX + line[5:], None))
        elif line.startswith("FAIL "):
            target, _, reason = line[5:].partition(" -> ")
            rows.append((PROBE_ROW_PREFIX + target,
                         reason or "the probe reported FAIL with no reason"))
    return rows


def check_probe(name, started):
    """(b)-(e) Run the HTTP probe inside the container and merge its verdicts into ours.

    `docker exec -i <name> python -u -` feeds the program over stdin: `-i` attaches stdin
    without asking for a tty (none is needed and none is available on a runner), the image's own
    interpreter runs it, and `docker exec` propagates the command's exit status — which is what
    lets the two consistency rows below tell "the probe reported failures" apart from "the probe
    died before it could report anything".
    """
    target = "the in-container probe's exit status agrees with its own report"
    marker_target = "the in-container probe ran to its end"
    if not started:
        return [
            ("the in-container HTTP probe", "not attempted: the container never started"),
        ], ""

    status, output = docker(
        ["exec", "-i", name, "python", "-u", "-"], PROBE_TIMEOUT, stdin_text=PROBE)
    if status is None:
        # Timed out, or docker is missing. Either way there are no verdicts to merge.
        return [("the in-container HTTP probe", output)], output

    rows = probe_report_rows(output)
    if not rows:
        # Exit status alone cannot be read here: a probe that printed nothing has told us
        # nothing, whatever it exited with. This is what a `docker exec` that could not start
        # the interpreter looks like, and what a truncated stdin looks like.
        return [("the in-container HTTP probe", (
            "it produced no report lines at all, so none of the HTTP checks ran. `docker exec` "
            "exited {}. Output:\n{}".format(status, excerpt(output))))], output

    reported_failures = any(reason is not None for _, reason in rows)
    if status != 0 and not reported_failures:
        rows.append((target, (
            "`docker exec` exited {} but every line the probe printed says ok — so it died "
            "after reporting and before finishing, and the report above is incomplete".format(
                status))))
    elif status == 0 and reported_failures:
        rows.append((target, (
            "the probe printed FAIL lines yet exited 0. Its failures are supposed to leave "
            "through SystemExit(1); an exit of 0 here means they no longer do, and this gate "
            "would have gone green on them")))
    else:
        rows.append((target, None))

    rows.append((marker_target, None if PROBE_MARKER in output else (
        "it never printed {!r}. The marker is on the probe's last line, so its absence means "
        "the program did not run to the end — a truncated stdin, or something that killed the "
        "interpreter mid-report".format(PROBE_MARKER))))
    return rows, output


def check_static_on_disk(name, started):
    """(e, second half) The built frontend is on disk, not merely answered for.

    Not a duplicate of the probe's asset checks: a missing file answers 404 there, so that side
    already catches an empty build. What this adds is independence from the HTTP layer — it
    still returns a verdict when uvicorn never came up, which is exactly the run where "is the
    frontend even in the image" is the question — and the file's SIZE, which nothing served over
    HTTP reports.
    """
    target = "{} exists inside the image".format(INDEX_PATH)
    if not started:
        return [(target, "not attempted: the container never started")]

    status, output = docker(["exec", name, "python", "-c", STATIC_PROBE], EXEC_TIMEOUT)
    if status is None:
        # No exit code at all: the docker CLI is missing, or this call ran out its timeout.
        # docker() already worded which; a non-zero exit means something else entirely and gets
        # its own message below.
        return [(target, output)]
    if status != 0:
        return [(target, (
            "`docker exec` exited {} — the container is no longer running, or the image has no "
            "python to run it with. Output:\n{}".format(status, excerpt(output))))]
    try:
        probe = json.loads(output.strip().splitlines()[-1])
    except (IndexError, ValueError) as error:
        return [(target, "the probe printed something unreadable ({}): {}".format(
            error, excerpt(output)))]
    if not isinstance(probe, dict):
        # Cannot happen through the probe's own code path, so it means something else wrote that
        # line. Handled rather than left to raise, because an AttributeError escaping here would
        # take the whole gate down with a traceback instead of a verdict.
        return [(target, "the probe printed {!r}, not an object".format(probe))]
    if not probe.get("index_exists"):
        return [(target, (
            "it does not. The frontend stage of the Dockerfile produced nothing that reached "
            "the runtime image, so this container serves an API and no app at all. {} contains: "
            "{!r}".format(STATIC_DIR, probe.get("entries"))))]
    if not probe.get("index_size"):
        return [(target, "it exists and is 0 bytes")]
    return [("{} ({} bytes)".format(target, probe["index_size"]), None)]


def check_survives_broker(name):
    """(f) The app must still be up, and its logs must say why it is unbothered.

    Everything above only works because an unreachable broker is survivable: there is no MQTT in
    CI, `lifespan` starts `mqtt_listener_loop()` as a background task, and that loop catches
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
        rows.append((running_target, "docker inspect exited {}: {}".format(
            status, excerpt(output))))
    else:
        state = output.strip()
        rows.append((running_target, None if state.startswith("true") else (
            "docker reports `Running ExitCode` = {!r}. The MQTT broker this gate points the app "
            "at does not exist on purpose, and the app is supposed to log a warning and retry — "
            "a container that exited instead means a broker outage now takes the service down "
            "with it, in production, where the broker is a real host that can reboot".format(
                state))))

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
            "{!r} never appeared in {} s. The container is up, so something is running — but the "
            "MQTT listener is not reporting the failure it must be having against {}, which "
            "means either the listener task is not being started at all or its failures are "
            "being swallowed silently. Logs:\n{}".format(
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
        print("{} is not set: this gate tests the image it is given and has no default, because "
              "a default would silently gate whichever image happened to be on the daemon".format(
                  IMAGE_ENV))
        raise SystemExit(1)
    name = os.environ.get(NAME_ENV)
    if not name:
        # No default here either, and this one is worth spelling out because a default would not
        # fail — it would work, quietly and wrongly, in two ways at once.
        # First, the cleanup: the workflow's `if: always()` step removes `<name>` and
        # `<name>-guard`, and it builds those names from the SAME variable. A dropped or
        # misspelled `env:` entry would leave this script naming its containers after the
        # fallback while the cleanup step went looking for the run-id ones, found nothing, and
        # swallowed the miss in its `|| true` — the gate stays green and the leak is permanent.
        # Second, collisions: the runner runs one docker daemon for every repository in the
        # fleet, so a constant fallback means two concurrent runs pick the SAME name — and
        # remove_container() below would then delete the other run's live container out from
        # under it.
        print("{} is not set: this gate names every container it starts after it, and a default "
              "would both hide containers from the workflow's cleanup step and make two "
              "concurrent runs collide on one name".format(NAME_ENV))
        raise SystemExit(1)

    rows = []
    transcripts = []

    rows.extend(check_image_contract(image))

    guard_rows, guard_output = check_missing_env_guard(image, name + GUARD_SUFFIX)
    transcripts.append(("the image run with no environment at all", guard_output))
    rows.extend(guard_rows)

    try:
        start_rows, started, start_output = start_container(image, name)
        transcripts.append(("`docker run -d` of the image under test", start_output))
        rows.extend(start_rows)

        probe_rows, probe_output = check_probe(name, started)
        transcripts.append(("the HTTP probe, from inside the container", probe_output))
        rows.extend(probe_rows)

        rows.extend(check_static_on_disk(name, started))

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
    # scrolls to the bottom for, and the container's own output is what turns a one-line verdict
    # into a diagnosis.
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
