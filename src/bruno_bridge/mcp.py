from pathlib import Path

from fastmcp import FastMCP

from bruno_bridge import Collection, bru_curl, bru_send


def build_server(root: Path) -> FastMCP:
    collection = Collection(root)
    mcp = FastMCP("bruno-bridge")

    @mcp.tool
    def discover() -> list[dict[str, str | None]]:
        """List every request file with its method and raw URL."""
        return [
            {"path": r.path, "method": r.method, "url": r.url}
            for r in collection.discover()
        ]

    @mcp.tool
    def curl(path: str, env: str) -> str:
        """Print the curl command for one request. Sends nothing."""
        return bru_curl(collection, path, env)

    @mcp.tool
    def run(path: str, env: str, timeout: float = 30.0) -> str:
        """Send one request and return the status, headers and body."""
        result = bru_send(collection, path, env, timeout)
        headers = "\n".join(f"{name}: {value}" for name, value in result.headers)
        body = result.body.decode("utf-8", errors="replace")
        return f"HTTP {result.status} {result.reason}\n{headers}\n\n{body}"

    return mcp
