"""FastAPI application powering the review UI.

Three panes:
    * Left   : filterable post list (selection updates the URL).
    * Center : read-only post detail with an "Open on LinkedIn" deep-link.
    * Right  : editable analysis form (subject, body, contacts, flags, ...).

The app is mounted under the same SQLite DB as the rest of the pipeline.
There is no auth — bind to localhost only.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from mailrocket.settings import settings
from mailrocket.storage.analysis_repo import status_counts, update_analysis
from mailrocket.storage.posts_repo import (
    SORT_OPTIONS,
    fetch_post_with_analyses,
    list_distinct_companies,
    list_posts_for_ui,
)

logger = logging.getLogger(__name__)

UI_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = UI_ROOT / "templates"
STATIC_DIR = UI_ROOT / "static"

VALID_STATUSES = ("all", "unanalyzed", "pending", "sent", "rejected")
DEFAULT_SORT = "latest"


class AnalysisUpdate(BaseModel):
    """Fields a reviewer is allowed to change on a `post_analysis` row.

    All fields optional; only the ones provided are written.
    """

    subject: str | None = None
    body: str | None = None
    company_name: str | None = None
    match_percentage: int | None = None
    experience_gap: int | None = None
    should_apply: bool | None = None
    final_decision: bool | None = None
    mail_sent: int | None = Field(default=None, ge=-1, le=1)
    contact_email: list[str] | str | None = None
    contact_number: list[str] | str | None = None
    application_link: list[str] | str | None = None


def _humanize_mail_sent(value: int | None) -> dict[str, str]:
    mapping = {
        -1: {"label": "Pending", "tone": "warn"},
        0: {"label": "Rejected", "tone": "danger"},
        1: {"label": "Sent", "tone": "ok"},
    }
    return mapping.get(value if value is not None else -1, {"label": "—", "tone": "muted"})


def _post_to_card(row: dict) -> dict:
    """Trim a list-row into something the template can iterate over."""
    text = (row.get("post_text") or "").strip().splitlines()
    snippet = " ".join(text)[:140]
    return {
        "uid": row["uid"],
        "author": row.get("author_name") or "Unknown",
        "query": row.get("query") or "",
        "post_date": row.get("post_date") or "",
        "snippet": snippet,
        "analysed": bool(row.get("analysed")),
        "match_percentage": row.get("match_percentage"),
        "company_name": row.get("company_name"),
        "should_apply": bool(row.get("should_apply")) if row.get("should_apply") is not None else None,
        "mail_sent": row.get("mail_sent"),
        "mail_status": _humanize_mail_sent(row.get("mail_sent")),
        "has_analysis": row.get("analysis_id") is not None,
    }


def _detail_payload(uid: int) -> dict:
    bundle = fetch_post_with_analyses(uid)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"post uid={uid} not found")
    post = bundle["post"]
    analyses = bundle["analyses"] or []
    primary = analyses[0] if analyses else None

    other = post.get("other_data") or {}
    if not isinstance(other, dict):
        other = {}

    return {
        "post": {
            "uid": post["uid"],
            "post_link": post.get("post_link") or "",
            "author_name": post.get("author_name") or "",
            "profile_url": post.get("profile_url") or "",
            "query": post.get("query") or "",
            "post_text": post.get("post_text") or "",
            "post_date": post.get("post_date") or "",
            "analysed": bool(post.get("analysed")),
            "inserted_at": post.get("inserted_at") or "",
            "hashtags": other.get("hashtags") or [],
            "reactions": other.get("reactions"),
            "comments": other.get("comments"),
        },
        "analyses": [
            {
                **a,
                "mail_status": _humanize_mail_sent(a.get("mail_sent")),
            }
            for a in analyses
        ],
        "primary": (
            {
                **primary,
                "mail_status": _humanize_mail_sent(primary.get("mail_sent")),
            }
            if primary
            else None
        ),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="MailRocket Review UI", version="0.1.0")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2, default=str)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(
        request: Request,
        status: str = Query("all"),
        q: str | None = Query(None),
        uid: int | None = Query(None),
        min_match: int = Query(0, ge=0, le=100),
        company: str | None = Query(None),
        sort: str = Query(DEFAULT_SORT),
    ) -> Any:
        status = status if status in VALID_STATUSES else "all"
        sort = sort if sort in SORT_OPTIONS else DEFAULT_SORT
        company_clean = (company or "").strip() or None

        rows = list_posts_for_ui(
            status=status,
            query=(q or None),
            min_match=min_match,
            company=company_clean,
            sort=sort,
        )
        cards = [_post_to_card(r) for r in rows]

        selected_uid = uid if uid is not None else (cards[0]["uid"] if cards else None)
        detail = _detail_payload(selected_uid) if selected_uid is not None else None

        # Params we want to keep when the user clicks a tab pill or a post.
        # Empty/default values are dropped so the URL stays clean.
        base_params: dict[str, str] = {}
        if q:
            base_params["q"] = q
        if min_match:
            base_params["min_match"] = str(min_match)
        if company_clean:
            base_params["company"] = company_clean
        if sort and sort != DEFAULT_SORT:
            base_params["sort"] = sort

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "cards": cards,
                "selected_uid": selected_uid,
                "detail": detail,
                "filter_status": status,
                "search_query": q or "",
                "min_match": min_match,
                "company_filter": company_clean or "",
                "sort_by": sort,
                "companies": list_distinct_companies(),
                "base_params": base_params,
                "counts": status_counts(),
                "db_path": str(settings.paths.db),
                "candidate_name": settings.candidate.full_name,
            },
        )

    @app.get("/api/posts")
    def api_posts(
        status: str = Query("all"),
        q: str | None = Query(None),
        min_match: int = Query(0, ge=0, le=100),
        company: str | None = Query(None),
        sort: str = Query(DEFAULT_SORT),
        limit: int = Query(500, ge=1, le=2000),
    ) -> JSONResponse:
        status = status if status in VALID_STATUSES else "all"
        sort = sort if sort in SORT_OPTIONS else DEFAULT_SORT
        rows = list_posts_for_ui(
            status=status,
            query=(q or None),
            min_match=min_match,
            company=(company or None),
            sort=sort,
            limit=limit,
        )
        return JSONResponse([_post_to_card(r) for r in rows])

    @app.get("/api/posts/{uid}")
    def api_post_detail(uid: int) -> JSONResponse:
        return JSONResponse(_detail_payload(uid))

    @app.patch("/api/analyses/{analysis_id}")
    def api_update_analysis(analysis_id: int, payload: AnalysisUpdate) -> JSONResponse:
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No fields provided")
        try:
            n = update_analysis(analysis_id, data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if n == 0:
            raise HTTPException(status_code=404, detail=f"analysis_id={analysis_id} not found")
        return JSONResponse({"updated": n, "fields": list(data.keys())})

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app


def run(host: str = "127.0.0.1", port: int = 8765, reload: bool = False) -> None:
    """Convenience runner used by `python -m mailrocket ui`."""
    import uvicorn

    uvicorn.run(
        "mailrocket.ui.server:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
