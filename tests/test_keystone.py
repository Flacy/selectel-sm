from __future__ import annotations

from typing import Any

import httpx
import pytest
from assertpy import assert_that

from selectel_sm._core import keystone
from selectel_sm.exceptions import AuthenticationError


def test_build_password_auth_is_project_scoped() -> None:
    body = keystone.build_password_auth(
        account_id="000000",
        username="svc",
        password="secret",
        project_name="test-project",
    )
    identity = body["auth"]["identity"]
    assert_that(identity["methods"]).is_equal_to(["password"])
    user = identity["password"]["user"]
    assert_that(user["name"]).is_equal_to("svc")
    assert_that(user["domain"]).is_equal_to({"name": "000000"})
    # The scope MUST be project (account scope is rejected by Secrets Manager).
    scope = body["auth"]["scope"]
    assert_that(scope).contains_key("project")
    assert_that(scope).does_not_contain_key("domain")
    assert_that(scope["project"]).is_equal_to(
        {"name": "test-project", "domain": {"name": "000000"}}
    )


def test_parse_token_reads_header_and_body(token_body: dict[str, Any]) -> None:
    response = httpx.Response(
        201,
        headers={keystone.SUBJECT_TOKEN_HEADER: "abc123"},
        json=token_body,
    )
    token = keystone.parse_token(response)
    assert_that(token.value).is_equal_to("abc123")
    assert_that(token.project.name).is_equal_to("test-project")
    assert_that(token.catalog.service("secrets-manager")).is_not_none()


def test_parse_token_missing_header_raises(token_body: dict[str, Any]) -> None:
    response = httpx.Response(201, json=token_body)
    with pytest.raises(AuthenticationError):
        keystone.parse_token(response)


def test_parse_token_invalid_body_raises() -> None:
    response = httpx.Response(
        201,
        headers={keystone.SUBJECT_TOKEN_HEADER: "abc"},
        content=b"not json",
    )
    with pytest.raises(AuthenticationError):
        keystone.parse_token(response)
