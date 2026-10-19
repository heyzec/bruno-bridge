from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl

from bruno_bridge.constants import METHODS, VAR_PATTERN, BruError
from bruno_bridge.collection import BruEntry, BruFile, Collection
from bruno_bridge.plan import BearerAuth, Body, JsonBody, Plan


class Scope:
    """Variable values for one request. Records names that have no value."""

    def __init__(self, values: dict[str, str], source: str):
        self.values: dict[str, str] = values
        self.source: str = source
        self.missing: set[str] = set()

    def expand(self, text: str, stack: tuple[str, ...] = ()) -> str:
        def substitute(match: re.Match[str]) -> str:
            name = match[1]
            if name in stack:
                raise BruError(f"{self.source}: variable '{name}' refers to itself")
            if name not in self.values:
                self.missing.add(name)
                return match[0]
            return self.expand(self.values[name], (*stack, name))

        return VAR_PATTERN.sub(substitute, text)

    def check(self) -> None:
        if self.missing:
            names = ", ".join(sorted(self.missing))
            raise BruError(f"{self.source}: unresolved variables: {names}")



def with_default_header(headers: list[tuple[str, str]], name: str, value: str) -> list[tuple[str, str]]:
    if any(h.lower() == name.lower() for h, _ in headers):
        return headers
    return [*headers, (name, value)]


def split_query(url: str, params: list[tuple[str, str]]) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Query params from params:query override same-named pairs already in the URL."""
    base, _, raw = url.partition("?")
    overridden = {key for key, _ in params}
    kept = [(k, v) for k, v in parse_qsl(raw, keep_blank_values=True) if k not in overridden]
    return base, (*kept, *params)


def request_method(request_bru: BruFile) -> tuple[str, dict[str, str]]:
    for name in METHODS:
        block = request_bru.get_block(name)
        if block is not None:
            return name.upper(), block.variables()
    raise BruError(f"{request_bru.path}: no HTTP method block")


def _variables(bru: BruFile, name: str) -> dict[str, str]:
    """Variables of the named block, or none if the file lacks it."""
    block = bru.get_block(name)
    return block.variables() if block is not None else {}


def _entries(bru: BruFile, name: str) -> list[BruEntry]:
    """Entries of the named block, or none if the file lacks it."""
    block = bru.get_block(name)
    return block.entries() if block is not None else []


class Planner:
    """A Planner is a Plan builder. It reads one .bru request, resolve variables (following inheritance rules of folders and collections) and returns a Plan.
    """

    def __init__(self, collection: Collection, relative: str, env: str):
        self.collection: Collection = collection
        self.relative_path: Path = collection.request_path(relative)
        self.request_bru: BruFile = collection.read(self.relative_path)
        self.collection_bru: BruFile = collection.read_optional(Path("collection.bru"))
        self.folders: list[BruFile] = collection.folder_files(self.relative_path)

        env_file = Path("environments") / f"{env}.bru"
        if not collection.exists(env_file):
            raise BruError(f"unknown environment '{env}'")

        method, fields = request_method(self.request_bru)
        self.method: str = method
        self.fields: dict[str, str] = fields

        # Lowest to highest priority: collection, environment, folders root->leaf, request.
        values: dict[str, str] = {}
        values |= _variables(self.collection_bru, "vars:pre-request")
        values |= _variables(collection.read(env_file), "vars")
        for folder in self.folders:
            values |= _variables(folder, "vars:pre-request")
        values |= _variables(self.request_bru, "vars:pre-request")
        self.scope: Scope = Scope(values, self.relative_path.as_posix())

    def build(self) -> Plan:
        url, query = self._url()
        headers = self._headers()
        auth = self._auth()
        body = self._body()
        self.scope.check()

        if isinstance(body, JsonBody):
            headers = with_default_header(headers, "Content-Type", "application/json")

        return Plan(
            source=self.relative_path.as_posix(),
            method=self.method,
            url=url,
            query=query,
            headers=tuple(headers),
            auth=auth,
            body=body,
        )

    def _url(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        if "url" not in self.fields:
            raise BruError(f"{self.relative_path}: request has no url")
        params = [
            (self.scope.expand(e.key), self.scope.expand(e.value))
            for e in _entries(self.request_bru, "params:query")
            if e.enabled
        ]
        return split_query(self.scope.expand(self.fields["url"]), params)

    def _headers(self) -> list[tuple[str, str]]:
        """Nearest level wins. Names match case-insensitively."""
        merged: dict[str, tuple[str, str]] = {}
        for layer in [self.collection_bru, *self.folders, self.request_bru]:
            for entry in _entries(layer, "headers"):
                if entry.enabled:
                    merged[entry.key.lower()] = (entry.key, self.scope.expand(entry.value))
        return list(merged.values())

    def _auth(self) -> BearerAuth | None:
        # Nearest level that declares a concrete mode wins; "inherit" defers upward.
        levels = [
            (self.fields.get("auth", "inherit"), self.request_bru),
            *((_variables(f, "auth").get("mode", "inherit"), f) for f in reversed(self.folders)),
            (_variables(self.collection_bru, "auth").get("mode", "inherit"), self.collection_bru),
        ]
        for mode, owner in levels:
            if mode == "inherit":
                continue
            if mode == "none":
                return None
            if mode == "bearer":
                token = _variables(owner, "auth:bearer").get("token")
                if token is None:
                    raise BruError(f"{owner.path}: bearer auth has no token")
                return BearerAuth(self.scope.expand(token))
            raise BruError(f"{owner.path}: unsupported auth mode '{mode}'")
        return None

    def _body(self) -> Body | None:
        kind = self.fields.get("body", "none")
        if kind == "none":
            return None

        if kind == "json":
            body_text = self.request_bru.get_data_as_json()
            if body_text is None:
                raise BruError(f"{self.request_bru.path}: body is json but has no body:json block")
            text = self.scope.expand(body_text)
            self.scope.check()
            try:
                data = json.loads(text)  # pyright: ignore[reportAny] (immediately re-serialized)
            except json.JSONDecodeError as exc:
                raise BruError(f"{self.request_bru.path}: body is not valid JSON: {exc}") from exc
            return JsonBody(json.dumps(data, ensure_ascii=False, separators=(",", ":")))

        raise BruError(f"{self.request_bru.path}: unsupported body '{kind}'")

