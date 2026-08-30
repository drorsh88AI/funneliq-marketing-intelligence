"""FunnelIQ API — skeleton (phase 1).

Only /health exists so far; it is public by design (see SPEC.md, permission
matrix). Routes, auth and static files arrive in phases 4 and 9.
"""

from fastapi import FastAPI

app = FastAPI(title="FunnelIQ API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
