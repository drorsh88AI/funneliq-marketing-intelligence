"""Tests for the three exception handlers wired in app/main.py (PHASE9.md
D7, checkpoint 4, criteria 14-17).

Built against a throwaway diagnostic app that registers the EXACT SAME
handler functions imported from app.main -- not a reimplementation --
with synthetic routes designed to trigger each exception type on demand.
This is the direct regression test for the empirical finding that made
D7 mandatory during planning: without these handlers, an unhandled
exception (or a response that fails its own response_model) reaches the
client as `text/plain "Internal Server Error"`, not the ErrorDetail JSON
body every 500/503 in the locked contract promises.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from pydantic import BaseModel

from app.main import (
    request_validation_exception_handler,
    response_validation_exception_handler,
    unhandled_exception_handler,
)


# Module-level on purpose: with `from __future__ import annotations`, FastAPI
# resolves a route's string annotations via typing.get_type_hints(), which
# looks the name up in the function's __globals__ -- a Pydantic model
# defined LOCALLY inside a function body is invisible to that lookup, and
# FastAPI silently falls back to treating the parameter as an unresolvable
# query param instead of a JSON body (verified empirically: produced
# loc=["query", "body"], "Field required", not the intended body-shape
# validation error).
class _Body(BaseModel):
    x: int


class _Resp(BaseModel):
    y: int


def _build_diagnostic_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(ResponseValidationError, response_validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.post("/validate", response_model=_Resp)
    def validate(body: _Body):
        return {"y": body.x}

    @app.post("/bad-response", response_model=_Resp)
    def bad_response(body: _Body):
        return {"y": "not-an-int"}  # fails _Resp's own schema -> ResponseValidationError

    @app.get("/boom")
    def boom():
        raise RuntimeError("simulated internal failure, file=/etc/secret.txt")

    return app


client = TestClient(_build_diagnostic_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Criterion 14 -- 500 = ErrorDetail JSON, not text/plain.
# ---------------------------------------------------------------------------


def test_unhandled_exception_is_500_error_detail_json_not_text_plain():
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Internal Server Error"}


# ---------------------------------------------------------------------------
# Criterion 16 -- ResponseValidationError -> 500 ErrorDetail.
# ---------------------------------------------------------------------------


def test_response_validation_error_is_500_error_detail():
    response = client.post("/bad-response", json={"x": 1})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Internal Server Error"}


# ---------------------------------------------------------------------------
# Criterion 15 -- 503 = ErrorDetail JSON. The 503 path itself is
# app/auth.py's own HTTPException(status_code=503, ...), already covered
# by tests/test_auth.py's gotrue-5xx/network-retryable tests (FastAPI's
# default HTTPException handler already returns {"detail": ...}) -- this
# is the direct proof that injecting a raw exception through the SAME
# generic-Exception path this file tests also comes back as ErrorDetail
# JSON, not text/plain, for the 500 family that D16 maps unmapped
# failures to.
# ---------------------------------------------------------------------------


def test_error_body_is_valid_error_detail_shape():
    from app.schemas import ErrorDetail

    response = client.get("/boom")
    ErrorDetail(**response.json())  # must not raise


# ---------------------------------------------------------------------------
# Criterion 17 -- no traceback, exception class name, file path, or input
# value anywhere in the body.
# ---------------------------------------------------------------------------


def test_no_traceback_class_name_path_or_input_leaks_into_body():
    response = client.get("/boom")
    text = response.text
    assert "RuntimeError" not in text
    assert "Traceback" not in text
    assert "secret.txt" not in text
    assert "simulated internal failure" not in text


def test_response_validation_failure_does_not_leak_the_bad_value():
    response = client.post("/bad-response", json={"x": 1})
    assert "not-an-int" not in response.text


# ---------------------------------------------------------------------------
# 422 shape -- loc/msg/type only, no input/ctx (the mechanism criteria
# 8-10 rely on for the real business routes).
# ---------------------------------------------------------------------------


def test_request_validation_error_body_has_only_loc_msg_type():
    response = client.post("/validate", json={"x": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"detail"}
    assert len(body["detail"]) == 1
    item = body["detail"][0]
    assert set(item.keys()) == {"loc", "msg", "type"}
    assert item["loc"] == ["body", "x"]


def test_request_validation_error_never_echoes_input_value():
    response = client.post("/validate", json={"x": "sensitive-looking-value"})
    assert "sensitive-looking-value" not in response.text
