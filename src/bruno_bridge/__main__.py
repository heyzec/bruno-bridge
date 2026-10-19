import argparse
from enum import StrEnum
import sys
from pathlib import Path

from bruno_bridge import CallResult, Collection, bru_curl, bru_send
from bruno_bridge.constants import DEFAULT_ENV, DEFAULT_TIMEOUT, BruError


class Command(StrEnum):
    DISCOVER = "discover"
    CURL = "curl"
    RUN = "run"
    MCP = "mcp"


class Args(argparse.Namespace):
    command: str
    collection: Path
    path: str
    env: str
    timeout: float


def handle_curl(collection: Collection, path: str, env: str) -> int:
    print(bru_curl(collection, path, env))
    return 0


def handle_discover(collection: Collection) -> int:
    for r in collection.discover():
        print(f"{r.path}\t{r.method}\t{r.url or ''}")
    return 0


def handle_run(collection: Collection, path: str, env: str, timeout: float) -> int:
    result: CallResult = bru_send(collection, path, env, timeout)
    print(f"HTTP {result.status} {result.reason}")
    for name, value in result.headers:
        print(f"{name}: {value}")
    print()
    print(result.body.decode("utf-8", errors="replace"))
    return 0


def handle_mcp(root: Path) -> int:
    # Imported here so the CLI works without the optional fastmcp extra.
    try:
        from bruno_bridge.mcp import build_server
    except ImportError:
        print(
            "error: fastmcp is not installed; install with: pip install 'bruno-bridge[mcp]'",
            file=sys.stderr,
        )
        return 1
    build_server(root).run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print or send a Bruno request."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--collection",
        type=Path,
        required=True,
        help="path to the Bruno collection root",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    # discover
    commands.add_parser(
        Command.DISCOVER,
        parents=[common],
        help="list every request file with its method and raw URL",
    )

    # curl
    curl = commands.add_parser(
        Command.CURL, parents=[common], help="print the curl command; sends nothing"
    )
    curl.add_argument(
        "path",
        help="path relative to the collection root",
    )
    curl.add_argument(
        "--env", default=DEFAULT_ENV, help=f"environment name (default: {DEFAULT_ENV})"
    )

    # run
    run = commands.add_parser(Command.RUN, parents=[common], help="send the request")
    run.add_argument("path", help="path relative to the collection root")
    run.add_argument(
        "--env", default=DEFAULT_ENV, help=f"environment name (default: {DEFAULT_ENV})"
    )
    run.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"seconds (default: {DEFAULT_TIMEOUT:g})",
    )

    # mcp
    commands.add_parser(
        Command.MCP,
        parents=[common],
        help="serve the collection as an MCP server over stdio",
    )

    args = parser.parse_args(argv, Args())
    collection = Collection(args.collection)
    command = Command(args.command)
    try:
        match command:
            case Command.DISCOVER:
                return handle_discover(collection)
            case Command.CURL:
                return handle_curl(collection, args.path, args.env)
            case Command.RUN:
                return handle_run(collection, args.path, args.env, args.timeout)
            case Command.MCP:
                return handle_mcp(args.collection)
    except BruError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
