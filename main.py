from random import randint
from fastmcp import FastMCP

mcp = FastMCP("Simple Calculator Server")

@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

@mcp.tool()
def random_number(minimum: int, maximum: int) -> int:
    """Return a random integer in the inclusive range."""
    if minimum > maximum:
        raise ValueError("minimum must be less than or equal to maximum")
    return randint(minimum, maximum)

@mcp.resource("server://info")
def server_info() -> str:
    """Return basic information about this MCP server."""
    return "Simple Calculator Server: add numbers and generate random integers."

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000,
    )