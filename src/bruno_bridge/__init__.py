import urllib.request

from bruno_bridge.collection import BruFile, Collection, DiscoveredRequest
from bruno_bridge.constants import DEFAULT_TIMEOUT, BruError
from bruno_bridge.consumers import CallResult, CurlConsumer, SendConsumer, UrllibConsumer
from bruno_bridge.planner import Planner


def bru_curl(collection: Collection, path: str, env: str) -> str:
    """The curl command for one request. Sends nothing."""
    return CurlConsumer().consume(Planner(collection, path, env).build())


def bru_request(collection: Collection, path: str, env: str) -> urllib.request.Request:
    """The urllib request for one request. Sends nothing."""
    return UrllibConsumer().consume(Planner(collection, path, env).build())


def bru_send(
    collection: Collection, path: str, env: str, timeout: float = DEFAULT_TIMEOUT
) -> CallResult:
    """Send one request and return what the server answered."""
    return SendConsumer(timeout).consume(Planner(collection, path, env).build())


__all__ = [
    "BruError",
    "BruFile",
    "CallResult",
    "Collection",
    "DiscoveredRequest",
    "bru_curl",
    "bru_request",
    "bru_send",
]
