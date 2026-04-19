"""Host-side USB helper service for Docker-backed deployments."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import tempfile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
import uvicorn

from endless_loader.config import Settings, load_settings
from endless_loader.models import PatchRecord
from endless_loader.services.deploy import DeploymentService
from endless_loader.services.usb import DeploymentError, HostUsbBackend, build_usb_backend


def create_helper_app(config_path: str | Path | None = None) -> FastAPI:
    settings = load_settings(config_path)
    host_settings = replace(settings, usb=replace(settings.usb, mode="host"))
    deployment = DeploymentService(
        build_usb_backend(host_settings.usb),
        log_path=host_settings.usb.log_path,
    )

    app = FastAPI(title="Endless Loader USB Helper")
    app.state.deployment = deployment

    @app.get("/healthz")
    def healthz():
        status = app.state.deployment.mount_status()
        return JSONResponse(
            {
                "status": "ok",
                "backend": "usb-helper",
                "usb": status.to_dict(),
            }
        )

    @app.get("/v1/usb/status")
    def usb_status():
        return JSONResponse(app.state.deployment.mount_status().to_dict())

    @app.post("/v1/usb/deploy")
    async def usb_deploy(
        file: UploadFile = File(...),
        display_name: str = Form(...),
        rel_path: str = Form(""),
    ):
        suffix = Path(file.filename or "patch.endl").suffix or ".endl"
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                temp_path = Path(handle.name)
                while True:
                    chunk = await file.read(65536)
                    if not chunk:
                        break
                    handle.write(chunk)
            patch = PatchRecord(
                rel_path=rel_path or (file.filename or "uploaded.endl"),
                abs_path=temp_path,
                filename=file.filename or "uploaded.endl",
                display_name=display_name,
                source_family="local_library",
            )
            outcome = app.state.deployment.deploy(patch)
            return JSONResponse(outcome.to_dict())
        except DeploymentError as exc:
            status = exc.status.to_dict() if exc.status else None
            return JSONResponse(
                {"error": str(exc), "usb": status},
                status_code=409,
            )
        finally:
            await file.close()
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    return app


def build_backend(settings: Settings) -> HostUsbBackend:
    return HostUsbBackend(settings.usb)


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="Run the Endless Loader USB helper.")
    parser.add_argument("--config", help="Path to config.toml", default=None)
    parser.add_argument("--host", help="Bind host", default="127.0.0.1")
    parser.add_argument("--port", help="Bind port", type=int, default=8755)
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload mode")
    args = parser.parse_args()

    app = create_helper_app(args.config)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    cli_main()
