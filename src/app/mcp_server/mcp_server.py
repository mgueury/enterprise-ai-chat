from typing import Any

from fastmcp import FastMCP  # Import FastMCP, the quickstart server base

mcp = FastMCP("MCP Server")  # Initialize an MCP server instance with a descriptive name

# The canonical sample data from Oracle's classic SCOTT.DEPT table.  This demo
# MCP server intentionally has no database dependency.
DEPARTMENTS: tuple[dict[str, Any], ...] = (
    {"deptno": 10, "dname": "ACCOUNTING", "loc": "NEW YORK"},
    {"deptno": 20, "dname": "RESEARCH", "loc": "DALLAS"},
    {"deptno": 30, "dname": "SALES", "loc": "CHICAGO"},
    {"deptno": 40, "dname": "OPERATIONS", "loc": "BOSTON"},
)

def log( s ): 
    print( s, flush=True )

@mcp.tool()
def send_email(to: str, subject: str, body: str) -> dict[str, str]:
    """Email sender tool"""
    log("<send_email>")
    log(f"<send_email>: to={to}, subject={subject}")

    return {
        "status": "sent",
        "message": f"Email sent to {to} with subject '{subject}'",
    }

@mcp.tool()
def get_dept() -> list[dict[str, Any]]:
    """Return the four static sample rows from Oracle's classic DEPT table."""
    log( "<get_dept>")
    # Return new dictionaries so a tool consumer cannot alter the module data.
    return [department.copy() for department in DEPARTMENTS]
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=2025)
