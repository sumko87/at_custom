import os
import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

AIRTABLE_API = "https://api.airtable.com/v0"

mcp = FastMCP("Airtable MCP")


def _client() -> httpx.Client:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        raise RuntimeError("AIRTABLE_PAT is not set")
    return httpx.Client(
        base_url=AIRTABLE_API,
        headers={"Authorization": f"Bearer {pat}"},
        timeout=30.0,
    )


@mcp.tool
def list_bases() -> dict:
    """List all Airtable bases the authenticated user can access."""
    with _client() as c:
        r = c.get("/meta/bases")
        r.raise_for_status()
        return r.json()


@mcp.tool
def list_records(base_id: str, table: str, max_records: int = 20) -> dict:
    """List records from a table. `table` may be a table name or table ID (tbl...)."""
    with _client() as c:
        r = c.get(f"/{base_id}/{table}", params={"maxRecords": max_records})
        r.raise_for_status()
        return r.json()


@mcp.tool
def create_record(base_id: str, table: str, fields: dict) -> dict:
    """Create one record. `fields` maps column names to values, e.g. {"Name": "Acme"}."""
    with _client() as c:
        r = c.post(f"/{base_id}/{table}", json={"fields": fields})
        r.raise_for_status()
        return r.json()


# if __name__ == "__main__":
#     mcp.run()  # stdio transport by default



@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port)

