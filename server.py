import os
import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.debug import DebugTokenVerifier
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import PlainTextResponse

AIRTABLE_API = "https://api.airtable.com/v0"
BASE_URL = os.environ["PUBLIC_BASE_URL"]  # https://at-custom.onrender.com

auth = OAuthProxy(
    upstream_authorization_endpoint="https://airtable.com/oauth2/v1/authorize",
    upstream_token_endpoint="https://airtable.com/oauth2/v1/token",
    upstream_client_id=os.environ["AIRTABLE_CLIENT_ID"],
    upstream_client_secret=os.environ["AIRTABLE_CLIENT_SECRET"],
    base_url=BASE_URL,
    redirect_path="/auth/callback",
    token_verifier=DebugTokenVerifier(),
    valid_scopes=["data.records:read", "data.records:write", "schema.bases:read"],
)

mcp = FastMCP("Airtable MCP", auth=auth)


def _headers() -> dict:
    token = get_access_token().token
    return {"Authorization": f"Bearer {token}"}


@mcp.tool
async def list_bases() -> dict:
    """List all Airtable bases the authenticated user can access."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.get("/meta/bases")
        r.raise_for_status()
        return r.json()


@mcp.tool
async def list_records(base_id: str, table: str, max_records: int = 20) -> dict:
    """List records from a table. `table` may be a table name or table ID (tbl...)."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.get(f"/{base_id}/{table}", params={"maxRecords": max_records})
        r.raise_for_status()
        return r.json()


@mcp.tool
async def create_record(base_id: str, table: str, fields: dict) -> dict:
    """Create one record. `fields` maps column names to values, e.g. {"Name": "Acme"}."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.post(f"/{base_id}/{table}", json={"fields": fields})
        r.raise_for_status()
        return r.json()


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port)
