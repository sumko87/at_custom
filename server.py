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


# ----- added tools (all use your existing 3 scopes) -----


@mcp.tool
async def whoami() -> dict:
    """Return the authenticated Airtable user's id and granted scopes."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.get("/meta/whoami")
        r.raise_for_status()
        return r.json()


@mcp.tool
async def get_base_schema(base_id: str) -> dict:
    """Get a base's full schema: every table with its fields (name, id, type) and views.
    Call this to discover exact table and field names before reading or writing records."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.get(f"/meta/bases/{base_id}/tables")
        r.raise_for_status()
        return r.json()


@mcp.tool
async def get_record(base_id: str, table: str, record_id: str) -> dict:
    """Get a single record by its id (rec...) from a table."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.get(f"/{base_id}/{table}/{record_id}")
        r.raise_for_status()
        return r.json()


@mcp.tool
async def search_records(
    base_id: str,
    table: str,
    filter_by_formula: str = "",
    fields: list[str] | None = None,
    sort: list[dict] | None = None,
    view: str = "",
    max_records: int = 100,
    page_size: int = 0,
    offset: str = "",
) -> dict:
    """Search/list records with full options. `filter_by_formula` is an Airtable formula
    (e.g. "{Status}='Active'"); `fields` limits returned columns; `sort` is e.g.
    [{"field": "Name", "direction": "asc"}]; pass `offset` from a prior response to page."""
    params: dict = {}
    if filter_by_formula:
        params["filterByFormula"] = filter_by_formula
    if view:
        params["view"] = view
    if max_records:
        params["maxRecords"] = max_records
    if page_size:
        params["pageSize"] = page_size
    if offset:
        params["offset"] = offset
    if fields:
        params["fields[]"] = fields
    if sort:
        for i, s in enumerate(sort):
            params[f"sort[{i}][field]"] = s["field"]
            params[f"sort[{i}][direction]"] = s.get("direction", "asc")
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.get(f"/{base_id}/{table}", params=params)
        r.raise_for_status()
        return r.json()


@mcp.tool
async def create_records(base_id: str, table: str, records: list[dict], typecast: bool = False) -> dict:
    """Create up to 10 records at once. `records` is a list of field maps,
    e.g. [{"Name": "Acme"}, {"Name": "Globex"}]. `typecast=True` lets Airtable coerce values."""
    payload: dict = {"records": [{"fields": f} for f in records]}
    if typecast:
        payload["typecast"] = True
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.post(f"/{base_id}/{table}", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool
async def update_record(base_id: str, table: str, record_id: str, fields: dict, typecast: bool = False) -> dict:
    """Partially update one record by id. Only the given `fields` change; the rest stay intact."""
    payload: dict = {"fields": fields}
    if typecast:
        payload["typecast"] = True
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.patch(f"/{base_id}/{table}/{record_id}", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool
async def update_records(base_id: str, table: str, records: list[dict], typecast: bool = False) -> dict:
    """Partially update up to 10 records. `records` is a list of
    {"id": "rec...", "fields": {...}} — only the listed fields change."""
    payload: dict = {"records": records}
    if typecast:
        payload["typecast"] = True
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.patch(f"/{base_id}/{table}", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool
async def delete_record(base_id: str, table: str, record_id: str) -> dict:
    """Delete one record by id (rec...)."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.delete(f"/{base_id}/{table}/{record_id}")
        r.raise_for_status()
        return r.json()


@mcp.tool
async def delete_records(base_id: str, table: str, record_ids: list[str]) -> dict:
    """Delete up to 10 records by id."""
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=_headers(), timeout=30.0) as c:
        r = await c.delete(f"/{base_id}/{table}", params={"records[]": record_ids})
        r.raise_for_status()
        return r.json()


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port)
