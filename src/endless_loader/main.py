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
from endless_loader.models import MountStatus, PatchRecord, RuntimeState
from endless_loader.services.companion import CompanionMetadataProvider
from endless_loader.services.deploy import DeploymentError, DeploymentService
from endless_loader.services.inputs import NullInputAdapter
from endless_loader.services.lcd import NullDisplayAdapter, build_display_adapter, build_patch_lines
from endless_loader.services.scanner import LibraryCatalog
from endless_loader.services.state import StateStore
from endless_loader.services.usb import build_usb_backend


@dataclass
class AppServices:
    settings: Settings
    templates: Jinja2Templates
    catalog: LibraryCatalog
    state_store: StateStore
    deployment: DeploymentService
    display: NullDisplayAdapter | object
    inputs: NullInputAdapter


@dataclass(frozen=True)
class UsbPresentation:
    badge_label: str
    tone: str
    headline: str
    guidance: str
    backend_label: str
    identity_label: str
    mountpoint_label: str
    verification_label: str
    cta_label: str
    cta_hint: str


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
        services = request.app.state.services
        catalog = services.catalog
        current_state = services.state_store.load()
        current_patch = catalog.find(current_state.current_patch_rel_path)
        hero_patch = _resolve_hero_patch(catalog, selected, current_state)
        groups = catalog.grouped(q)
        hero_knob_index = _default_knob_index(hero_patch)
        lcd_preview = build_patch_lines(hero_patch) if hero_patch else (" " * 16, " " * 16)
        mount_status = services.deployment.mount_status()
        usb_ui = _present_usb_status(mount_status)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "settings": services.settings,
                "groups": groups,
                "hero_patch": hero_patch,
                "hero_knob_index": hero_knob_index,
                "current_patch": current_patch,
                "current_state": current_state,
                "selected_patch_rel_path": selected,
                "hero_state": _hero_state(hero_patch, current_patch, selected),
                "mount_status": mount_status,
                "usb_ui": usb_ui,
                "companion_source": catalog.companion_source,
                "notice": notice,
                "error": error,
                "query": q,
                "lcd_preview": lcd_preview,
            },
        )

    @app.post("/load")
    def load_patch(
        request: Request,
        rel_path: str = Form(...),
        q: str = Form(""),
        selected: str | None = Form(None),
    ):
        services = request.app.state.services
        patch = services.catalog.find(rel_path)
        if patch is None:
            target = _redirect_target(
                "/",
                selected=selected or rel_path,
                q=q,
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
            target = _redirect_target(
                "/",
                selected=selected or rel_path,
                q=q,
                error=str(exc),
            )
            return RedirectResponse(target, status_code=303)

        services.state_store.save(
            RuntimeState.loaded(
                patch,
                deployed_at=outcome.deployed_at,
                message=outcome.message,
            )
        )
        services.display.show_ready(patch)
        target = _redirect_target(
            "/",
            selected=selected or rel_path,
            q=q,
            notice=outcome.message,
        )
        return RedirectResponse(target, status_code=303)

    @app.post("/rescan")
    def rescan_library(
        q: str = Form(""),
        selected: str | None = Form(None),
    ):
        services = app.state.services
        services.catalog.reload()
        return RedirectResponse(
            _redirect_target(
                "/",
                selected=selected,
                q=q,
                notice="Library rescanned.",
            ),
            status_code=303,
        )

    @app.get("/healthz")
    def healthz(request: Request):
        services = request.app.state.services
        usb_status = services.deployment.mount_status()
        payload = {
            "status": "ok",
            "library_root": str(services.settings.library_root),
            "patch_count": len(services.catalog.patches),
            "mount_ready": usb_status.ready,
            "usb": usb_status.to_dict(),
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
        deployment=DeploymentService(
            build_usb_backend(settings.usb),
            log_path=settings.usb.log_path,
        ),
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


def _hero_state(
    hero_patch: PatchRecord | None,
    current_patch: PatchRecord | None,
    selected: str | None,
) -> str:
    if hero_patch is None:
        return "preview"
    if current_patch and current_patch.rel_path == hero_patch.rel_path:
        return "live"
    if selected and selected == hero_patch.rel_path:
        return "selected"
    return "preview"


def _redirect_target(path: str, **params: str | None) -> str:
    filtered = {key: value for key, value in params.items() if value}
    if not filtered:
        return path
    return f"{path}?{urlencode(filtered)}"


def _present_usb_status(status: MountStatus) -> UsbPresentation:
    tone = "ready" if status.ready and status.state == "mounted" else "pending" if status.ready else "error"
    badge_label = status.label
    headline = status.label
    guidance = status.detail

    if status.state == "identity_missing":
        badge_label = "Identity Needed"
        headline = "Set the Endless USB identity"
        guidance = "Configure usb.expected_uuid or usb.expected_label in config.toml before loading patches."
    elif status.state == "no_match":
        badge_label = "Endless Not Found"
        headline = "Connect the Endless storage volume"
        guidance = "Put the pedal in USB storage mode, then reconnect it or verify the configured label or UUID."
    elif status.state == "multiple_matches":
        badge_label = "Multiple Matches"
        headline = "More than one USB volume matches"
        guidance = "Use usb.expected_uuid to target one Endless volume and avoid ambiguous writes."
    elif status.state == "discovered":
        badge_label = "Ready to Mount"
        headline = "Target volume found"
        guidance = "The matched volume will mount automatically when you load a patch."
    elif status.state == "mounted":
        badge_label = "Mounted"
        headline = "Volume is mounted and writable"
        guidance = "The matched Endless volume is ready for a verified patch write."
    elif status.state == "read_only":
        badge_label = "Read-Only"
        headline = "Volume is mounted read-only"
        guidance = "Remount the Endless volume read-write before loading a patch."
    elif status.state == "mount_failed":
        badge_label = "Mount Failed"
        headline = "Automatic mount failed"
        guidance = "The volume was identified, but the host could not mount it automatically."
    elif status.state == "mount_missing":
        badge_label = "Mount Unresolved"
        headline = "Mountpoint could not be confirmed"
        guidance = "The host reported a mount, but no writable mountpoint was resolved."
    elif status.state == "helper_offline":
        badge_label = "Helper Offline"
        headline = "Host USB helper is unavailable"
        guidance = "Start endless-loader-usb-helper on the host before using helper mode."

    backend_label = {
        "host": "Direct Host USB",
        "helper": "Host USB Helper",
    }.get(status.backend, status.backend.upper())

    identity_parts: list[str] = []
    if status.expected_uuid:
        identity_parts.append(f"UUID {status.expected_uuid}")
    if status.expected_label:
        identity_parts.append(f"Label {status.expected_label}")
    identity_label = " • ".join(identity_parts) if identity_parts else "Not configured"

    if status.mountpoint:
        mountpoint_label = status.mountpoint
    elif status.ready:
        mountpoint_label = "Will mount automatically on load"
    else:
        mountpoint_label = "Unavailable until a single target volume is ready"

    verification_label = (
        "Last deploy verified"
        if status.last_verified
        else "Read-back hash enabled"
    )

    cta_label = "Load This Patch" if status.ready else "USB Not Ready"
    cta_hint = (
        "Load will mount, copy, and verify the selected patch."
        if status.ready and status.state == "discovered"
        else "Ready for a verified patch write."
        if status.ready
        else guidance
    )

    return UsbPresentation(
        badge_label=badge_label,
        tone=tone,
        headline=headline,
        guidance=guidance,
        backend_label=backend_label,
        identity_label=identity_label,
        mountpoint_label=mountpoint_label,
        verification_label=verification_label,
        cta_label=cta_label,
        cta_hint=cta_hint,
    )


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
