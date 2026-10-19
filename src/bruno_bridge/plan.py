from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True)
class BearerAuth:
    """A bearer token. Plan.target_headers turns it into the Authorization header."""

    token: str


# Only bearer auth supported for now
Auth = BearerAuth  # | BasicAuth | ...


@dataclass(frozen=True)
class JsonBody:
    """A request body as compact JSON text, with comments and trailing commas removed."""

    text: str


# Only JSON supported for now
Body = JsonBody  # | MultipartBody | FileBody | ...


@dataclass(frozen=True)
class Plan:
    """A fully resolved representation of a .bru request."""

    source: str
    method: str
    url: str
    query: tuple[tuple[str, str], ...]
    headers: tuple[tuple[str, str], ...]
    auth: BearerAuth | None
    body: Body | None

    def target_url(self) -> str:
        """The URL with the query string appended."""
        if self.query:
            return self.url + "?" + urlencode(self.query)
        return self.url

    def target_headers(self) -> list[tuple[str, str]]:
        """Headers as sent. An explicit Authorization header overrides the auth block."""
        headers = list(self.headers)
        has_authorization = any(name.lower() == "authorization" for name, _ in headers)
        if self.auth is not None and not has_authorization:
            headers.append(("Authorization", f"Bearer {self.auth.token}"))
        return headers
