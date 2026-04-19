"""FastAPI entrypoint for Endless Loader."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from endless_loader.config import Settings, load_settings
from endless_loader.models import PatchRecord, RuntimeState
from endless_loader.services.companion import CompanionMetadataProvider
from endless_loader.services.deploy import DeploymentError, DeploymentService
from endless_loader.services.inputs import NullInputAdapter
from endless_loader.services.lcd import NullDisplayAdapter, build_display_adapter, build_patch_lines
from endless_loader.services.scanner import LibraryCatalog
from endless_loader.services.state import StateStore


@dataclass
class AppServices:
    settings: Settings
    templates: Jinja2Templates
    catalog: LibraryCatalog
    state_store: StateStore
    deployment: DeploymentService
    display: NullDisplayAdapter | object
    inputs: NullInputAdapter


def create_app(config_path: str | Path | None = None) -> FastAPI:
    settings = load_settings(config_path)
    templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
    services = build_services(settings, templates)

    app = FastAPI(title="Endless Loader")
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).with_name("static"))),
        name="static",
    )
    app.state.services = services

    @app.get("/")
    def index(
        request: Request,
        selected: str | None = None,
        q: str = "",
        notice: str | None = None,
        error: str | None = None,
    ):
        catalog = request.app.state.services.catalog
        current_state = request.app.state.services.state_store.load()
        current_patch = catalog.find(current_state.current_patch_rel_path)
        hero_patch = _resolve_hero_patch(catalog, selected, current_state)
        groups = catalog.grouped(q)
        hero_knob_index = _default_knob_index(hero_patch)
        lcd_preview = build_patch_lines(hero_patch) if hero_patch else (" " * 16, " " * 16)
        query_suffix = f"&q={q}" if q else ""
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "settings": request.app.state.services.settings,
                "groups": groups,
                "hero_patch": hero_patch,
                "hero_knob_index": hero_knob_index,
                "current_patch": current_patch,
                "current_state": current_state,
                "mount_status": request.app.state.services.deployment.mount_status(),
                "companion_source": catalog.companion_source,
                "notice": notice,
                "error": error,
                "query": q,
                "query_suffix": query_suffix,
                "lcd_preview": lcd_preview,
            },
        )

    @app.post("/load")
    def load_patch(request: Request, rel_path: str = Form(...)):
        services = request.app.state.services
        patch = services.catalog.find(rel_path)
        if patch is None:
            target = _redirect_target(
                "/",
                selected=rel_path,
                error=f"Patch not found: {rel_path}",
            )
            return RedirectResponse(target, status_code=303)

        services.display.show_loading(patch)
        try:
            outcome = services.deployment.deploy(patch)
        except DeploymentError as exc:
            state = RuntimeState(
                current_patch_rel_path=rel_path,
                current_display_name=patch.display_name,
                last_status="error",
                last_message=str(exc),
            )
            services.state_store.save(state)
            services.display.show_error(str(exc))
            target = _redirect_target("/", selected=rel_path, error=str(exc))
            return RedirectResponse(target, status_code=303)

        services.state_store.save(
            RuntimeState.loaded(
                patch,
                deployed_at=outcome.deployed_at,
                message=outcome.message,
            )
        )
        services.display.show_ready(patch)
        target = _redirect_target("/", selected=rel_path, notice=outcome.message)
        return RedirectResponse(target, status_code=303)

    @app.post("/rescan")
    def rescan_library():
        services = app.state.services
        services.catalog.reload()
        return RedirectResponse(_redirect_target("/", notice="Library rescanned."), status_code=303)

    @app.get("/healthz")
    def healthz(request: Request):
        services = request.app.state.services
        payload = {
            "status": "ok",
            "library_root": str(services.settings.library_root),
            "patch_count": len(services.catalog.patches),
            "mount_ready": services.deployment.mount_status().ready,
            "companion_source": services.catalog.companion_source,
            "lcd_backend": services.display.__class__.__name__,
        }
        return JSONResponse(payload)

    return app


def build_services(settings: Settings, templates: Jinja2Templates) -> AppServices:
    companion = CompanionMetadataProvider(settings.companion)
    catalog = LibraryCatalog(settings.library_root, companion)
    catalog.reload()
    return AppServices(
        settings=settings,
        templates=templates,
        catalog=catalog,
        state_store=StateStore(settings.state_path),
        deployment=DeploymentService(settings.pedal_mount_path),
        display=build_display_adapter(settings.lcd),
        inputs=NullInputAdapter(),
    )


def _resolve_hero_patch(
    catalog: LibraryCatalog,
    selected: str | None,
    current_state: RuntimeState,
) -> PatchRecord | None:
    return (
        catalog.find(selected)
        or catalog.find(current_state.current_patch_rel_path)
        or catalog.first()
    )


def _default_knob_index(patch: PatchRecord | None) -> int:
    if patch is None:
        return 0
    for index, knob in enumerate(patch.knobs):
        if knob.active:
            return index
    return 0


def _redirect_target(path: str, **params: str | None) -> str:
    filtered = {key: value for key, value in params.items() if value}
    if not filtered:
        return path
    return f"{path}?{urlencode(filtered)}"


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="Run the Endless Loader web server.")
    parser.add_argument("--config", help="Path to config.toml", default=None)
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload mode")
    args = parser.parse_args()

    settings = load_settings(args.config)
    app = create_app(args.config)
    uvicorn.run(
        app,
        host=settings.web.host,
        port=settings.web.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    cli_main()
