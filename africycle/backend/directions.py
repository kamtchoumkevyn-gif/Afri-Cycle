"""Road directions from a seller to a buyer, on foot or by motorbike/car.

Routes come from the free OSRM routing servers run by FOSSGIS for OpenStreetMap
(routing.openstreetmap.de, the same ones openstreetmap.org uses). Their rules: at most
one request a second, an honest User-Agent, and credit on the map, so requests go
through this server, which identifies the app, waits its turn, and remembers recent
answers. Set ROUTING_URL to use another OSRM server (for example your own).
"""
import contextlib
import json
import math
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request

from i18n import N_, _

try:
    import fcntl  # lets the server processes on one machine take turns (Linux and macOS)
except ImportError:  # Windows: local development runs a single process anyway
    fcntl = None

ROUTING_URL = (os.environ.get("ROUTING_URL")
               or "https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/{coords}")
PROFILES = {"foot": "foot", "car": "car"}  # motorbikes and tricycles follow the car roads
USER_AGENT = "Africycle/1.0 (scrap-collection marketplace, Cameroon; https://github.com/kamtchoumkevyn-gif/Afri-Cycle)"
CREDIT = N_("Route: OSRM (FOSSGIS) · map data © OpenStreetMap contributors")  # the pages translate it
MAX_KM = 300  # longer trips aren't what the app is for, and are slow to work out
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
QUEUE_SECONDS = 15  # how long a request waits for its turn before giving up
CACHE_SECONDS = 10 * 60
TIMEOUT_SECONDS = 12

# Render may run several server processes (gunicorn workers, see WEB_CONCURRENCY), each
# with its own memory, so the time of the last request is also kept in this file, and a
# lock on it lets one process at a time ask the routing server.
TURN_FILE = os.path.join(tempfile.gettempdir(), "africycle-routing-turn")

_cache = {}
_lock = threading.Lock()
_last_request_at = 0.0


class NoRoute(Exception):
    """The routing server found no road between the two points."""


class RoutingUnavailable(Exception):
    """The routing server couldn't be reached or gave an unusable answer."""


# ---- Instructions, in the language of the person asking ----

COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]

# Whole sentences, so each language can put the road name where it belongs. The second
# form of each is used when the road has a name.
HEAD = {
    "north": (N_("Head north"), N_("Head north on {road}")),
    "north-east": (N_("Head north-east"), N_("Head north-east on {road}")),
    "east": (N_("Head east"), N_("Head east on {road}")),
    "south-east": (N_("Head south-east"), N_("Head south-east on {road}")),
    "south": (N_("Head south"), N_("Head south on {road}")),
    "south-west": (N_("Head south-west"), N_("Head south-west on {road}")),
    "west": (N_("Head west"), N_("Head west on {road}")),
    "north-west": (N_("Head north-west"), N_("Head north-west on {road}")),
}
TURNS = {
    "sharp right": (N_("Turn sharp right"), N_("Turn sharp right onto {road}")),
    "right": (N_("Turn right"), N_("Turn right onto {road}")),
    "slight right": (N_("Bear right"), N_("Bear right onto {road}")),
    "straight": (N_("Go straight on"), N_("Go straight onto {road}")),
    "slight left": (N_("Bear left"), N_("Bear left onto {road}")),
    "left": (N_("Turn left"), N_("Turn left onto {road}")),
    "sharp left": (N_("Turn sharp left"), N_("Turn sharp left onto {road}")),
    "uturn": (N_("Make a U-turn"), N_("Make a U-turn onto {road}")),
}
KEEP = {"left": (N_("Keep left"), N_("Keep left onto {road}")),
        "right": (N_("Keep right"), N_("Keep right onto {road}"))}
END_OF_ROAD = {"left": (N_("At the end of the road, turn left"), N_("At the end of the road, turn left onto {road}")),
               "right": (N_("At the end of the road, turn right"), N_("At the end of the road, turn right onto {road}"))}
ROUNDABOUT_EXIT = (N_("At the roundabout, take exit {exit}"), N_("At the roundabout, take exit {exit} onto {road}"))
ROUNDABOUT = (N_("Go around the roundabout"), N_("Go around the roundabout onto {road}"))
LEAVE_ROUNDABOUT = (N_("Leave the roundabout"), N_("Leave the roundabout onto {road}"))
CONTINUE = (N_("Continue straight on"), N_("Continue on {road}"))


def road_name(step):
    name, ref = step.get("name") or "", step.get("ref") or ""
    if name and ref and ref not in name:
        return f"{name} ({ref})"
    return name or ref


def instruction(step, language=None):
    """One OSRM step as a sentence, e.g. "Turn left onto Rue Joss", in the language asked for
    (that of the request when none is given)."""
    maneuver = step.get("maneuver") or {}
    kind = maneuver.get("type", "turn")
    modifier = maneuver.get("modifier") or "straight"
    road = road_name(step)
    side = "left" if "left" in modifier else "right"

    def say(sentences, **values):
        return _(sentences[1] if road else sentences[0], language, road=road, **values)

    if step.get("mode") == "ferry":
        return _("Take the ferry", language)
    if kind == "depart":
        heading = COMPASS[int(((maneuver.get("bearing_after") or 0) % 360) / 45 + 0.5) % 8]
        return say(HEAD[heading])
    if kind == "arrive":
        return _("You have arrived", language)
    if kind in ("roundabout", "rotary"):
        exit_number = maneuver.get("exit")
        return say(ROUNDABOUT_EXIT, exit=exit_number) if exit_number else say(ROUNDABOUT)
    if kind in ("exit roundabout", "exit rotary"):
        return say(LEAVE_ROUNDABOUT)
    if modifier == "uturn":
        return say(TURNS["uturn"])
    if kind in ("fork", "merge", "on ramp", "off ramp"):
        return say(KEEP[side])
    if kind == "end of road":
        return say(END_OF_ROAD[side])
    if kind in ("new name", "continue", "notification", "use lane") and modifier == "straight":
        return say(CONTINUE)
    return say(TURNS.get(modifier, CONTINUE))


def summarise(answer, mode, language=None):
    """The parts of an OSRM answer the app needs, with coordinates as [lat, lng]."""
    if not isinstance(answer, dict):
        raise RoutingUnavailable("not JSON")
    if answer.get("code") == "NoRoute":
        raise NoRoute()
    if answer.get("code") != "Ok" or not answer.get("routes"):
        raise RoutingUnavailable(str(answer.get("code")))
    try:
        route = answer["routes"][0]
        line = [[round(lat, 6), round(lng, 6)] for lng, lat in route["geometry"]["coordinates"]]
        steps = []
        for leg in route["legs"]:
            for step in leg["steps"]:
                lng, lat = step["maneuver"]["location"]
                steps.append({
                    "text": instruction(step, language),
                    "type": step["maneuver"].get("type", ""),
                    "modifier": step["maneuver"].get("modifier", ""),
                    "distance": round(step.get("distance", 0)),
                    "duration": round(step.get("duration", 0)),
                    "at": [round(lat, 6), round(lng, 6)],
                })
        return {"mode": mode, "distance": round(route["distance"]), "duration": round(route["duration"]),
                "line": line, "steps": steps, "credit": CREDIT}
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise RoutingUnavailable(f"unexpected answer: {error}") from error


# ---- Asking the routing server ----

def fetch_json(url, referer=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            return json.loads(error.read())  # OSRM explains problems such as NoRoute in JSON
        except ValueError:
            raise RoutingUnavailable(f"HTTP {error.code}") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise RoutingUnavailable(str(error)) from error


def straight_km(a, b):
    rad = math.pi / 180
    h = (math.sin((b[0] - a[0]) * rad / 2) ** 2 +
         math.cos(a[0] * rad) * math.cos(b[0] * rad) * math.sin((b[1] - a[1]) * rad / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def _lock_turn_file(deadline):
    """The turn file, locked for this process; None where it can't be shared (then only
    this process's own lock and clock keep requests apart)."""
    if fcntl is None:
        return None
    try:
        # O_NOFOLLOW: never write through a link someone else put in the shared temp folder
        handle = os.fdopen(os.open(TURN_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "r+")
    except OSError:
        return None
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:  # another process is asking right now
            if time.time() >= deadline:
                handle.close()
                raise RoutingUnavailable("busy")
            time.sleep(0.05)
        except OSError:
            handle.close()
            return None


def _read_time(handle):
    try:
        handle.seek(0)
        return float(handle.read().strip() or 0)
    except (OSError, ValueError):
        return 0.0


def _write_time(handle, value):
    try:
        handle.seek(0)
        handle.truncate()
        handle.write(repr(value))
        handle.flush()
    except OSError:
        pass


@contextlib.contextmanager
def _turn():
    """One request at a time to the routing server, at most one a second (its rule),
    shared by all of this machine's server processes."""
    global _last_request_at
    deadline = time.time() + QUEUE_SECONDS
    if not _lock.acquire(timeout=QUEUE_SECONDS):
        raise RoutingUnavailable("busy")
    handle = None
    try:
        handle = _lock_turn_file(deadline)
        last = max(_last_request_at, _read_time(handle) if handle else 0.0)
        # never more than the gap itself, even if the clock was moved back since
        wait = min(MIN_SECONDS_BETWEEN_REQUESTS, MIN_SECONDS_BETWEEN_REQUESTS - (time.time() - last))
        if wait > 0:
            time.sleep(wait)
        try:
            yield
        finally:
            _last_request_at = time.time()
            if handle:
                _write_time(handle, _last_request_at)
    finally:
        if handle:
            handle.close()  # also lets the next process go
        _lock.release()


def get_route(start, end, mode="foot", referer=None, language=None):
    """Road route between two [lat, lng] points, with directions in the language asked for.
    Raises NoRoute or RoutingUnavailable."""
    key = (mode, round(start[0], 4), round(start[1], 4), round(end[0], 4), round(end[1], 4))  # about 10 m
    saved = _cache.get(key)
    if saved and saved[0] > time.time():
        return summarise(saved[1], mode, language)

    coords = f"{start[1]:.6f},{start[0]:.6f};{end[1]:.6f},{end[0]:.6f}"
    url = ROUTING_URL.format(profile=PROFILES[mode], coords=coords) + "?overview=full&geometries=geojson&steps=true"
    with _turn():
        answer = fetch_json(url, referer)

    route = summarise(answer, mode, language)  # raises for an unusable answer, which isn't kept
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time() + CACHE_SECONDS, answer)  # the answer: directions in any language
    return route
