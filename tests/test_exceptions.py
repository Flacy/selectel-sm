from __future__ import annotations

from assertpy import assert_that

from selectel_sm.exceptions import (
    APIError,
    AuthenticationError,
    EndpointNotFoundError,
    NotFoundError,
    SelectelSMError,
)


def test_all_errors_derive_from_base() -> None:
    for exc in (APIError, AuthenticationError, EndpointNotFoundError, NotFoundError):
        assert_that(issubclass(exc, SelectelSMError)).is_true()


def test_api_subclass_carries_status_code() -> None:
    assert_that(NotFoundError.status_code).is_equal_to(404)
    err = NotFoundError("missing")
    assert_that(err.status_code).is_equal_to(404)


def test_api_error_explicit_status_overrides_default() -> None:
    err = APIError("teapot", status_code=418)
    assert_that(err.status_code).is_equal_to(418)


def test_endpoint_not_found_lists_available_regions() -> None:
    err = EndpointNotFoundError("secrets-manager", "ru-99", "public", ["ru-7", "ru-2"])
    assert_that(err.available_regions).contains("ru-7", "ru-2")
    assert_that(str(err)).contains("ru-7").contains("ru-99")
