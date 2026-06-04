import os
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.debug import DebugTokenVerifier
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import PlainTextResponse

AIRTABLE_API = "https://api.airtable.com/v0"
BASE_URL = os.environ["PUBLIC_BASE_URL"]

SCOPES = [
    "data.records:read",
    "data.records:write",
    "data.recordComments:read",
    "data.recordComments:write",
    "schema.bases:read",
    "schema.bases:write",
    "user.email:read",
]

auth = OAuthProxy(
    upstream_authorization_endpoint="https://airtable.com/oauth2/v1/authorize",
    upstream_token_endpoint="https://airtable.com/oauth2/v1/token",
    upstream_client_id=os.environ["AIRTABLE_CLIENT_ID"],
    upstream_client_secret=os.environ["AIRTABLE_CLIENT_SECRET"],
    base_url=BASE_URL,
    redirect_path="/auth/callback",
    token_verifier=DebugTokenVerifier(),
    valid_scopes=SCOPES,
)

mcp = FastMCP("Airtable MCP")


async def _request(method: str, path: str, *, params: dict | None = None,
                   json: dict | None = None) -> Any:
    token = get_access_token().token
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=AIRTABLE_API, headers=headers, timeout=30.0) as c:
        r = await c.request(method, path, params=params, json=json)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(f"Airtable API error {r.status_code}: {detail}")
        return r.json() if r.content else {"success": True}


# ---------- Identity & discovery ----------

@mcp.tool
async def whoami() -> dict:
    """Return the authenticated Airtable user's id, email, and granted scopes."""
    return await _request("GET", "/meta/whoami")


@mcp.tool
async def list_bases() -> dict:
    """List all Airtable bases the user can access, with their base ids and names."""
    return await _request("GET", "/meta/bases")


@mcp.tool
async def get_base_schema(base_id: str) -> dict:
    """Get a base's full schema: every table with its fields (name, id, type) and views.
    Call this first to discover exact table and field names before reading or writing."""
    return await _request("GET", f"/meta/bases/{base_id}/tables")


# ---------- Records: read ----------

@mcp.tool
async def list_records(
    base_id: str,
    table: str,
    filter_by_formula: str = "",
    fields: list[str] | None = None,
    sort: list[dict[str, str]] | None = None,
    view: str = "",
    max_records: int = 100,
    page_size: int = 0,
    offset: str = "",
) -> dict:
    """List records from a table (name or tbl... id). Optional:
    `filter_by_formula` (Airtable formula), `fields` (subset of field names),
    `sort` (e.g. [{"field": "Name", "direction": "asc"}]), `view`, `max_records`,
    `page_size`, and `offset` (pass the `offset` from a prior response to page through results)."""
    params: dict[str, Any] = {}
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
    return await _request("GET", f"/{base_id}/{table}", params=params)


@mcp.tool
async def get_record(base_id: str, table: str, record_id: str) -> dict:
    """Get one record by its id (rec...) from a table."""
    return await _request("GET", f"/{base_id}/{table}/{record_id}")


# ---------- Records: write ----------

@mcp.tool
async def create_records(base_id: str, table: str, records: list[dict[str, Any]],
                         typecast: bool = False) -> dict:
    """Create up to 10 records. `records` is a list of field maps, e.g.
    [{"Name": "Acme", "Stage": "Lead"}]. `typecast=True` lets Airtable coerce values
    and create new select options on the fly."""
    payload: dict[str, Any] = {"records": [{"fields": f} for f in records]}
    if typecast:
        payload["typecast"] = True
    return await _request("POST", f"/{base_id}/{table}", json=payload)


@mcp.tool
async def update_records(base_id: str, table: str, records: list[dict[str, Any]],
                         typecast: bool = False) -> dict:
    """Partially update up to 10 records. `records` is a list of
    {"id": "rec...", "fields": {...}} — only listed fields change; the rest are untouched."""
    payload: dict[str, Any] = {"records": records}
    if typecast:
        payload["typecast"] = True
    return await _request("PATCH", f"/{base_id}/{table}", json=payload)


@mcp.tool
async def delete_records(base_id: str, table: str, record_ids: list[str]) -> dict:
    """Delete up to 10 records by id (rec...)."""
    return await _request("DELETE", f"/{base_id}/{table}", params={"records[]": record_ids})


# ---------- Comments ----------

@mcp.tool
async def list_comments(base_id: str, table: str, record_id: str) -> dict:
    """List comments on a record."""
    return await _request("GET", f"/{base_id}/{table}/{record_id}/comments")


@mcp.tool
async def create_comment(base_id: str, table: str, record_id: str, text: str) -> dict:
    """Add a comment to a record."""
    return await _request("POST", f"/{base_id}/{table}/{record_id}/comments",
                          json={"text": text})


# ---------- Schema editing (needs schema.bases:write) ----------

@mcp.tool
async def create_table(base_id: str, name: str, fields: list[dict[str, Any]],
                       description: str = "") -> dict:
    """Create a table. `fields` is a list of field specs, e.g.
    [{"name": "Name", "type": "singleLineText"}, {"name": "Notes", "type": "multilineText"}].
    The first field becomes the primary field."""
    payload: dict[str, Any] = {"name": name, "fields": fields}
    if description:
        payload["description"] = description
    return await _request("POST", f"/meta/bases/{base_id}/tables", json=payload)


@mcp.tool
async def create_field(base_id: str, table_id: str, name: str, type: str,
                       options: dict[str, Any] | None = None, description: str = "") -> dict:
    """Add a field to a table. `type` e.g. "singleLineText", "number", "singleSelect",
    "checkbox", "date". Some types require `options` (e.g. select choices)."""
    payload: dict[str, Any] = {"name": name, "type": type}
    if options:
        payload["options"] = options
    if description:
        payload["description"] = description
    return await _request("POST", f"/meta/bases/{base_id}/tables/{table_id}/fields", json=payload)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port)
