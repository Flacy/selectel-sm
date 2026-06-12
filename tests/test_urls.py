from __future__ import annotations

from assertpy import assert_that

from selectel_sm._core import urls


def test_normalize_collapses_double_slash_and_trailing() -> None:
    result = urls.normalize("https://cloud.api.selcloud.ru//secrets-manager/")
    assert_that(result).is_equal_to("https://cloud.api.selcloud.ru/secrets-manager")


def test_normalize_leaves_clean_url_untouched() -> None:
    url = "https://host/secrets-manager"
    assert_that(urls.normalize(url)).is_equal_to(url)


def test_join_appends_version_and_path() -> None:
    result = urls.join("https://host//secrets-manager/", "v1", "my-secret")
    assert_that(result).is_equal_to("https://host/secrets-manager/v1/my-secret")


def test_join_splits_segments_with_slashes() -> None:
    result = urls.join("https://host/secrets-manager", "v1", "name/versions")
    assert_that(result).is_equal_to("https://host/secrets-manager/v1/name/versions")


def test_join_with_empty_path() -> None:
    result = urls.join("https://host//secrets-manager/", "v1", "")
    assert_that(result).is_equal_to("https://host/secrets-manager/v1")


def test_join_trailing_slash() -> None:
    result = urls.join("https://host//secrets-manager/", "v1", "", trailing_slash=True)
    assert_that(result).is_equal_to("https://host/secrets-manager/v1/")


def test_join_trailing_slash_not_duplicated() -> None:
    result = urls.join("https://host/secrets-manager", "v1", "name", trailing_slash=True)
    assert_that(result).is_equal_to("https://host/secrets-manager/v1/name/")
