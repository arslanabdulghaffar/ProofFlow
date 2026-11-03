"""Trusted health surface, with admission closed until deployed gates are implemented.

Liveness proves only that the ASGI application can respond. It is deliberately
separate from readiness: a healthy Python process is not a verified worker or
an authorized provider. There is no configuration switch to bypass these gates.
"""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="ProofFlow",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class Liveness(BaseModel):
    status: Literal["alive"] = "alive"


class Unready(BaseModel):
    status: Literal["not_ready"] = "not_ready"
    reason: Literal["infrastructure_not_verified"] = "infrastructure_not_verified"


@app.get("/health/live", response_model=Liveness)
async def live() -> Liveness:
    return Liveness()


@app.get("/health/ready", response_model=Unready, status_code=503)
async def ready() -> Unready:
    # Replace only when real, freshness-checked dependency and admission checks
    # exist. An environment flag, stored PASS, or operator assertion is insufficient.
    return Unready()
