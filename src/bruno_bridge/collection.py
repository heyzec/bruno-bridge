from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from bruno_bridge.constants import METHODS, BruError


@dataclass(frozen=True)
class BruEntry:
    """Represents one `key: value` line from a .bru block."""

    key: str
    value: str
    enabled: bool

    @classmethod
    def parse(cls, line: str) -> BruEntry:
        enabled = not line.startswith("~")  # disabled lines start with ~
        key, sep, value = line.removeprefix("~").partition(":")
        if not sep:
            raise BruError(f"malformed entry: {line!r}")
        return cls(key.strip(), value.strip(), enabled)


@dataclass(frozen=True)
class BruBlock:
    """Represents one named block of a .bru file, as raw text."""

    text: str

    @classmethod
    def parse(cls, lines: list[str]) -> BruBlock:
        return cls("\n".join(line.removeprefix("  ") for line in lines))

    def entries(self) -> list[BruEntry]:
        """Only applicable to key/value blocks such as headers, params:query, vars and auth."""
        lines = self.text.splitlines()
        return [BruEntry.parse(line) for line in lines if line.strip()]

    def variables(self) -> dict[str, str]:
        return {e.key: e.value for e in self.entries() if e.enabled}


def strip_json_comments(text: str) -> str:
    """Remove // comments and trailing commas that sit outside JSON strings."""

    def skip_blank_and_comments(text: str, i: int) -> int:
        """Index of the next character at or after i that is not whitespace or a // comment."""
        while i < len(text):
            if text[i].isspace():
                i += 1
            elif text.startswith("//", i):
                end = text.find("\n", i)
                i = len(text) if end == -1 else end
            else:
                break
        return i

    def closes_next(text: str, comma: int) -> bool:
        """True when the next significant character after a comma closes an object or array."""
        j = skip_blank_and_comments(text, comma + 1)
        return j < len(text) and text[j] in "}]"

    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            out.append(ch)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            continue
        elif ch == "," and closes_next(text, i):
            # Bruno accepts a comma before a closing bracket; JSON does not.
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


@dataclass
class BruFile:
    """Represents a parsed .bru file."""

    path: Path
    blocks: dict[str, BruBlock]

    @classmethod
    def parse(cls, text: str) -> dict[str, BruBlock]:
        blocks: dict[str, BruBlock] = {}
        name: str | None = None
        lines: list[str] = []
        for line in text.splitlines():
            if name is None:
                if line.endswith("{") and not line.startswith(" "):
                    name, lines = line[:-1].strip(), []
            elif line == "}":
                blocks[name] = BruBlock.parse(lines)
                name = None
            else:
                lines.append(line)
        if name is not None:
            raise BruError(f"block '{name}' is not closed")
        return blocks

    def get_block(self, name: str) -> BruBlock | None:
        """The named block, or None if the file has no such block."""
        return self.blocks.get(name)

    def get_data_as_json(self) -> str | None:
        """The body:json block as JSON text, with // comments and trailing commas removed.

        Variables are not expanded. Returns None if the file has no body:json block.
        """
        block = self.get_block("body:json")
        return None if block is None else strip_json_comments(block.text)


@dataclass(frozen=True)
class DiscoveredRequest:
    """A request file found by Collection.discover. The URL is the raw template, unresolved."""

    path: str
    method: str
    url: str | None


class Collection:
    """Represents a Bruno collection rooted at one directory."""

    def __init__(self, root: Path):
        self.root: Path = root

    @classmethod
    def from_path(cls, path: str | Path) -> Collection:
        """A Collection rooted at the given directory."""
        return cls(Path(path))

    def discover(self) -> list[DiscoveredRequest]:
        """Returns every request file under root, sorted by path."""
        found: list[DiscoveredRequest] = []
        for path in self.root.rglob("*.bru"):
            relative = path.relative_to(self.root)
            if any(part.startswith(".") for part in relative.parts):
                continue
            try:
                bru = self.read(relative)
            except (BruError, OSError, UnicodeDecodeError) as exc:
                warnings.warn(f"skipped {relative.as_posix()}: {exc}", stacklevel=2)
                continue
            for method in METHODS:
                block = bru.get_block(method)
                if block is not None:
                    url = block.variables().get("url")
                    found.append(DiscoveredRequest(relative.as_posix(), method.upper(), url))
                    break
        return sorted(found, key=lambda r: r.path)

    def request_path(self, relative: str) -> Path:
        root = self.root.resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise BruError(f"{relative}: path is outside the collection")
        if path.suffix != ".bru" or not path.is_file():
            raise BruError(f"{relative}: no such .bru request")
        return path.relative_to(root)

    def exists(self, relative: Path) -> bool:
        return self._inside(relative).is_file()

    def read(self, relative: Path) -> BruFile:
        """Parse one .bru file. Raises BruError if it is missing or outside the root."""
        return self._load(self._inside(relative))

    def read_optional(self, relative: Path) -> BruFile:
        """Parse the file if it exists; otherwise return an empty BruFile."""
        path = self._inside(relative)
        return self._load(path) if path.is_file() else BruFile(path, {})

    def folder_files(self, relative: Path) -> list[BruFile]:
        """folder.bru files from the collection root down to the request's folder."""
        folders: list[BruFile] = []
        current = Path()
        for part in relative.parent.parts:
            current = current / part
            folders.append(self.read_optional(current / "folder.bru"))
        return folders

    def _inside(self, relative: Path) -> Path:
        root = self.root.resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise BruError(f"{relative}: path is outside the collection")
        return path

    def _load(self, path: Path) -> BruFile:
        try:
            blocks = BruFile.parse(path.read_text(encoding="utf-8"))
        except BruError as exc:
            raise BruError(f"{path}: {exc}") from exc
        return BruFile(path, blocks)
