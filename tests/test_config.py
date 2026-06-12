from __future__ import annotations

import pytest
from assertpy import assert_that

from selectel_sm.config import IDENTITY_URL_RU, Config


def test_region_is_required() -> None:
    with pytest.raises(ValueError):
        Config(region="")


def test_defaults() -> None:
    config = Config(region="ru-7")
    assert_that(config.identity_url).is_equal_to(IDENTITY_URL_RU)
    assert_that(config.interface).is_equal_to("public")
    assert_that(config.sm_base_url).is_none()
    assert_that(config.verify).is_true()


def test_overrides() -> None:
    config = Config(region="kz-1", interface="internal", sm_base_url="https://x/sm")
    assert_that(config.region).is_equal_to("kz-1")
    assert_that(config.interface).is_equal_to("internal")
    assert_that(config.sm_base_url).is_equal_to("https://x/sm")
