# bruno-bridge

Turn Bruno collections into a programmatic API client.

## Impetus
[Bruno](https://www.usebruno.com/) is more of a test runner than an API client<sup>[1](#footnotes)</sup>. While its GUI allows one to run a single request with Super+Enter, the CLI `bruno-cli` is collection-oriented. It runs multiple requests with test assertions, and reports the test results, with no straightfoward way to get the structured response data for the request<sup>[2](#footnotes)</sup>.

At the same time, Bruno has a great UI. There is no good alternative that solves this problem without sacrificing Bruno's UI.
- [Postman](https://www.postman.com/) and [Insomnia](https://insomnia.rest/)'s CLI also have a similar limitation of being test runners.
- [Hurl](https://hurl.dev/) is request-oriented, but lacks a GUI.

bruno-bridge wraps a Bruno collection as a reusable API client, available as a library, a CLI, and an MCP server. You keep Bruno’s UI and collection format as the source of truth.

## Usage

Firstly, install using a Python package manager (e.g. pip):
```sh
pip install bruno-bridge # (or bruno-bridge[mcp] if MCP needed)
```

### As a library
```python
from bruno_bridge import Collection, bru_send

collection = Collection.from_path("path/to/collection")
result = bru_send(collection, "path/from/collection/root/get-user.bru", env="test")

print(result.status, result.reason)
print(result.body.decode("utf-8"))
```

### As a CLI
```sh
# List every request with its method and raw URL
python -m bruno_bridge discover --collection path/to/collection

# Print the curl command for a request
python -m bruno_bridge curl --collection path/to/collection "path/from/collection/root/get-user.bru" --env test

# Send the request and print the response
python -m bruno_bridge run --collection path/to/collection "path/from/collection/root/get-user.bru" --env test --timeout 10
```

### As an MCP server
Example for Claude Code:
```sh
claude mcp add bruno-bridge --scope user -- python -m bruno_bridge mcp --collection path/to/collection
```

For Nix users (no installation required):
```sh
claude mcp add bruno-bridge --scope user -- nix run flake:https://github.com/heyzec/bruno-bridge mcp --collection /path/to/collection
```

## Footnotes
1. Many people call Bruno an API client. I use the term more narrowly, for something you can invoke to send one request and receive the response. By that measure, Bruno’s GUI is less of an API client than curl, and bruno-cli is less of one still.
2. You could use `bru run <file> --reporter-json results.json` and then parse the JSON file, but that is not ideal.
