# Python MCP SDK: Custom Headers for Streamable HTTP Transport

A comprehensive guide for implementing custom HTTP headers with the Python MCP SDK, covering both server-side and client-side implementations.

## Table of Contents

- [Overview](#overview)
- [Server-Side Implementation](#server-side-implementation)
  - [Using FastMCP with get_http_headers()](#1-using-fastmcp-with-get_http_headers)
  - [FastMCP Middleware for Authentication](#2-fastmcp-middleware-for-authentication)
  - [Production Configuration with Stateless Mode](#3-production-configuration-with-stateless-mode)
  - [Low-Level Server with Custom Header Access](#4-low-level-server-with-custom-header-access)
- [Client-Side Implementation](#client-side-implementation)
  - [Using FastMCP Client with Custom Headers](#1-using-fastmcp-client-with-custom-headers)
  - [Using Official SDK's streamablehttp_client](#2-using-official-sdks-streamablehttp_client)
  - [Client with Dynamic Headers](#3-client-with-dynamic-headers)
  - [Using LangChain MCP Adapters with Headers](#4-using-langchain-mcp-adapters-with-headers)
- [Complete Working Example](#complete-working-example)
- [Key Points](#key-points)
- [Troubleshooting](#troubleshooting)

---

## Overview

There are two main approaches to working with custom headers in Python MCP:

1. **FastMCP** (recommended) - Higher-level, more Pythonic approach
2. **Low-level SDK** - More control but more boilerplate

Custom headers are essential for:
- Authentication (Bearer tokens, API keys)
- Multi-tenancy (tenant IDs)
- Request tracing (correlation IDs)
- Client identification (version, user-agent)

---

## Server-Side Implementation

### 1. Using FastMCP with `get_http_headers()`

FastMCP provides `get_http_headers` from `fastmcp.server.dependencies` to access HTTP headers in your tools:

```python
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

mcp = FastMCP("my-server")

@mcp.tool()
async def my_authenticated_tool(data: str) -> str:
    """A tool that reads custom headers."""
    # Get all HTTP headers from the current request
    headers = get_http_headers(include_all=True)
    
    # Access specific headers
    auth_header = headers.get("authorization", "")
    custom_header = headers.get("x-custom-header", "")
    api_key = headers.get("x-api-key", "")
    
    # Use the header values
    if not auth_header.startswith("Bearer "):
        return "Error: Missing or invalid authorization"
    
    token = auth_header.removeprefix("Bearer ").strip()
    return f"Processed {data} for token: {token[:8]}..."

# Run with streamable HTTP transport
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

### 2. FastMCP Middleware for Authentication

For authentication middleware that validates headers on every tool call, use FastMCP's `Middleware` class:

```python
import asyncio
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import ToolError

class AuthMiddleware(Middleware):
    """Middleware to validate authentication headers."""
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        headers = get_http_headers()
        header = headers.get("authorization")
        
        if not header:
            raise ToolError("Access denied: missing authorization header")
        
        if not header.startswith("Bearer "):
            raise ToolError("Access denied: invalid token format")
        
        token = header.removeprefix("Bearer ").strip()
        user_id = await self.verify_token(token)
        
        if not user_id:
            raise ToolError("Access denied: invalid token")
        
        # Store user info in context for tools to access
        context.fastmcp_context.set_state("user_id", user_id)
        
        return await call_next(context)
    
    async def verify_token(self, token: str) -> str | None:
        """Verify token and return user ID."""
        # Replace with your actual token verification logic
        await asyncio.sleep(0)  # Simulate async operation
        if token == "valid-token-123":
            return "user_456"
        return None


# Create server with middleware
mcp = FastMCP("authenticated-server")
mcp.add_middleware(AuthMiddleware())

@mcp.tool()
async def get_user_data(ctx) -> dict:
    """Get data for the authenticated user."""
    user_id = ctx.get_state("user_id")
    return {"user_id": user_id, "data": "sensitive information"}

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0", 
        port=8000,
        mount_path="/mcp"
    )
```

### 3. Production Configuration with Stateless Mode

For production deployments that need horizontal scaling:

```python
import os
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

mcp = FastMCP(
    "production-server",
    stateless_http=True  # Enable stateless mode for horizontal scaling
)

# Configure server with environment variables
config = {
    "host": os.getenv("MCP_HOST", "0.0.0.0"),
    "port": int(os.getenv("MCP_PORT", 8000)),
    "path": "/mcp",
}

@mcp.tool()
async def secure_operation(data: str) -> dict:
    """Secure operation that validates API key header."""
    headers = get_http_headers()
    api_key = headers.get("x-api-key")
    
    if not api_key or not validate_api_key(api_key):
        return {"error": "Invalid API key", "success": False}
    
    return {"result": f"Processed: {data}", "success": True}

def validate_api_key(key: str) -> bool:
    """Validate the API key."""
    valid_keys = os.getenv("VALID_API_KEYS", "").split(",")
    return key in valid_keys

if __name__ == "__main__":
    mcp.run(transport="streamable-http", **config)
```

### 4. Low-Level Server with Custom Header Access

For more control, use the low-level server with Starlette:

```python
import asyncio
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response
from contextvars import ContextVar

from mcp.server.lowlevel import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
import mcp.types as types

# Context variable to store request headers
current_headers: ContextVar[dict] = ContextVar("current_headers", default={})

server = Server("header-aware-server")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_request_info",
            description="Get information from request headers",
            inputSchema={"type": "object", "properties": {}},
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_request_info":
        headers = current_headers.get()
        auth = headers.get("authorization", "none")
        custom = headers.get("x-custom-header", "none")
        return [types.TextContent(
            type="text",
            text=f"Auth: {auth[:20]}..., Custom: {custom}"
        )]
    raise ValueError(f"Unknown tool: {name}")

async def handle_mcp(request: Request) -> Response:
    # Capture headers and store in context variable
    headers_dict = dict(request.headers)
    current_headers.set(headers_dict)
    
    transport = StreamableHTTPServerTransport(
        mcp_endpoint="/mcp",
        is_json_response_enabled=True,
    )
    
    await server.connect(transport)
    return await transport.handle_request(request)

app = Starlette(routes=[
    Route("/mcp", handle_mcp, methods=["GET", "POST", "DELETE"]),
])
```

---

## Client-Side Implementation

### 1. Using FastMCP Client with Custom Headers

Use `StreamableHttpTransport` with custom headers:

```python
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

async def main():
    # Create transport with custom headers
    transport = StreamableHttpTransport(
        "http://localhost:8000/mcp",
        headers={
            "Authorization": "Bearer your-token-here",
            "X-API-Key": "your-api-key",
            "X-Custom-Header": "custom-value",
        }
    )
    
    # Initialize client with the transport
    client = Client(transport=transport)
    
    async with client:
        print(f"Connected: {client.is_connected()}")
        
        # List available tools
        tools = await client.list_tools()
        print(f"Tools: {[t.name for t in tools]}")
        
        # Call a tool
        result = await client.call_tool("my_tool", {"data": "test"})
        print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Using Official SDK's `streamablehttp_client`

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    # Connect with custom headers using httpx auth or headers
    async with streamablehttp_client(
        "http://localhost:8000/mcp",
        headers={
            "Authorization": "Bearer my-secret-token",
            "X-API-Key": "api-key-123",
            "X-Tenant-ID": "tenant-abc",
        }
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            # List tools
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")
            
            # Call a tool
            result = await session.call_tool("secure_operation", {"data": "test"})
            print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Client with Dynamic Headers

For scenarios where headers need to change (e.g., token refresh):

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

class TokenManager:
    """Manages authentication tokens with refresh capability."""
    
    def __init__(self, initial_token: str):
        self.token = initial_token
    
    async def refresh_token(self) -> str:
        """Refresh the token when needed."""
        # Implement your token refresh logic here
        self.token = "new-refreshed-token"
        return self.token
    
    def get_headers(self) -> dict:
        """Get current headers with the latest token."""
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Client-Version": "1.0.0",
        }

async def main():
    token_manager = TokenManager("initial-token")
    
    async with streamablehttp_client(
        "http://localhost:8000/mcp",
        headers=token_manager.get_headers()
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Use the session...
            tools = await session.list_tools()
            print(f"Tools: {[t.name for t in tools.tools]}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 4. Using LangChain MCP Adapters with Headers

When using LangChain's MCP adapters, you can include custom headers in the connection configuration:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

# Configure client with custom headers for HTTP transport
client = MultiServerMCPClient({
    "my_server": {
        "transport": "http",  # or "streamable_http"
        "url": "http://localhost:8000/mcp",
        "headers": {
            "Authorization": "Bearer token-123",
            "X-Custom-Header": "value",
        }
    }
})

# Use the client with LangChain agents...
```

---

## Complete Working Example

Here's a complete example with both server and client that you can run locally.

### Server (server.py)

```python
"""MCP Server with custom header support."""
import os
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

mcp = FastMCP("header-demo-server", stateless_http=True)

# Valid API keys (in production, use a database or secrets manager)
VALID_API_KEYS = {"key-123", "key-456", "key-789"}

@mcp.tool()
async def echo_headers() -> dict:
    """Echo back the received headers (sanitized)."""
    headers = get_http_headers(include_all=True)
    
    # Return sanitized header info
    return {
        "has_authorization": "authorization" in headers,
        "has_api_key": "x-api-key" in headers,
        "user_agent": headers.get("user-agent", "unknown"),
        "custom_header": headers.get("x-custom-header", "not provided"),
    }

@mcp.tool()
async def secure_data(query: str) -> dict:
    """Get secure data - requires valid API key."""
    headers = get_http_headers()
    api_key = headers.get("x-api-key", "")
    
    if api_key not in VALID_API_KEYS:
        return {"error": "Invalid or missing API key", "success": False}
    
    # Simulated secure data
    return {
        "success": True,
        "query": query,
        "data": {"secret": "This is protected data"},
    }

@mcp.tool()
async def get_user_context() -> dict:
    """Get context from custom headers."""
    headers = get_http_headers()
    
    return {
        "tenant_id": headers.get("x-tenant-id", "default"),
        "request_id": headers.get("x-request-id", "none"),
        "client_version": headers.get("x-client-version", "unknown"),
    }

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
    )
```

### Client (client.py)

```python
"""MCP Client with custom headers."""
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    # Define custom headers
    custom_headers = {
        "Authorization": "Bearer user-token-abc",
        "X-API-Key": "key-123",
        "X-Tenant-ID": "tenant-xyz",
        "X-Request-ID": "req-12345",
        "X-Client-Version": "2.0.0",
        "X-Custom-Header": "my-custom-value",
    }
    
    print("Connecting to MCP server with custom headers...")
    print(f"Headers: {list(custom_headers.keys())}")
    
    async with streamablehttp_client(
        "http://localhost:8000/mcp",
        headers=custom_headers
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print(f"\nAvailable tools: {[t.name for t in tools.tools]}")
            
            # Test 1: Echo headers
            print("\n--- Testing echo_headers ---")
            result = await session.call_tool("echo_headers", {})
            print(f"Result: {result.content[0].text if result.content else result.structuredContent}")
            
            # Test 2: Secure data access
            print("\n--- Testing secure_data ---")
            result = await session.call_tool("secure_data", {"query": "SELECT * FROM users"})
            print(f"Result: {result.content[0].text if result.content else result.structuredContent}")
            
            # Test 3: User context
            print("\n--- Testing get_user_context ---")
            result = await session.call_tool("get_user_context", {})
            print(f"Result: {result.content[0].text if result.content else result.structuredContent}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Running the Example

1. Install dependencies:
   ```bash
   pip install mcp fastmcp
   ```

2. Start the server:
   ```bash
   python server.py
   ```

3. In another terminal, run the client:
   ```bash
   python client.py
   ```

---

## Key Points

| Aspect | Recommendation |
|--------|----------------|
| **Server-side header access** | Use `get_http_headers()` from `fastmcp.server.dependencies` |
| **Client-side headers** | Pass via `headers` parameter when creating the transport |
| **Production scaling** | Use `stateless_http=True` for horizontal scaling |
| **Security** | Always validate authentication headers before processing sensitive requests |
| **Middleware** | Use FastMCP's `Middleware` class for cross-cutting concerns like auth |

---

## Troubleshooting

### Common Issues

1. **Headers not received on server**
   - Ensure you're using `include_all=True` in `get_http_headers()`
   - Check that the client is actually sending the headers
   - Verify CORS settings if using browser-based clients

2. **Session ID header issues**
   - There's a known issue (#1063 on GitHub) about `mcp-session-id` headers not being received properly in some FastMCP configurations
   - Consider using `stateless_http=True` as a workaround

3. **Authentication failures**
   - Verify header names are lowercase when accessing them (HTTP headers are case-insensitive, but Python dicts are case-sensitive)
   - Check that the `Authorization` header format matches what your server expects

4. **CORS issues with browser clients**
   - Add CORS middleware to expose the `Mcp-Session-Id` header:
   ```python
   from starlette.middleware.cors import CORSMiddleware
   
   app = CORSMiddleware(
       app,
       allow_origins=["*"],
       allow_methods=["GET", "POST", "DELETE"],
       expose_headers=["Mcp-Session-Id"],
   )
   ```

### Debugging Tips

```python
# Server-side: Log all received headers
@mcp.tool()
async def debug_headers() -> dict:
    headers = get_http_headers(include_all=True)
    print(f"Received headers: {headers}")  # Log to server console
    return {"headers": list(headers.keys())}

# Client-side: Verify headers before sending
print(f"Sending headers: {custom_headers}")
```

---

## References

- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCP Specification - Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP Authorization Specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)