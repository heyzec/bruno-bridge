from __future__ import annotations

import http.client
import shlex
from typing import IO, override
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from email.message import Message
from dataclasses import dataclass
from bruno_bridge.constants import DEFAULT_TIMEOUT, BruError
from bruno_bridge.plan import Plan


class PlanConsumer[T](ABC):
    """Acts on a Plan and returns T as result type."""

    @abstractmethod
    def consume(self, call: Plan) -> T: ...


class CurlConsumer(PlanConsumer[str]):
    """Turns a Plan into a curl command."""

    @override
    def consume(self, call: Plan) -> str:
        args = ["curl"]
        if call.method != "GET" or call.body is not None:
            args += ["-X", call.method]

        args.append(call.target_url())
        for name, value in call.target_headers():
            args += ["-H", f"{name}: {value}"]

        if call.body is not None:
            args += ["--data-raw", call.body.text]

        return " ".join(shlex.quote(arg) for arg in args)


class UrllibConsumer(PlanConsumer[urllib.request.Request]):
    """Builds a urllib.request.Request from a Plan for urlopen. Sends nothing."""

    @override
    def consume(self, call: Plan) -> urllib.request.Request:
        body = call.body.text.encode("utf-8") if call.body is not None else None
        return urllib.request.Request(
            call.target_url(),
            data=body,
            headers=dict(call.target_headers()),
            method=call.method,
        )


@dataclass(frozen=True)
class CallResult:
    """What the server answered. Non-2xx answers are results, not errors."""

    status: int
    reason: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


class SendConsumer(PlanConsumer[CallResult]):
    """Sends a Plan over HTTP and returns what the server answered. Raises BruError on transport failure."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        """Report redirects instead of following them, as curl does without -L."""

        @override
        def redirect_request(
            self,
            req: urllib.request.Request,
            fp: IO[bytes],
            code: int,
            msg: str,
            headers: Message,
            newurl: str,
        ):
            return None

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout: float = timeout

    @override
    def consume(self, call: Plan) -> CallResult:
        request = UrllibConsumer().consume(call)
        opener = urllib.request.build_opener(self._NoRedirect)
        try:
            with opener.open(
                request, timeout=self.timeout
            ) as response:  # pyright: ignore[reportAny]
                assert isinstance(response, http.client.HTTPResponse)
                return CallResult(
                    response.status,
                    response.reason,
                    tuple(response.headers.items()),
                    response.read(),
                )
        except urllib.error.HTTPError as exc:
            return CallResult(
                exc.code, exc.reason, tuple(exc.headers.items()), exc.read()
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BruError(
                f"SendConsumer failed to send: {getattr(exc, 'reason', exc)}"
            ) from exc
