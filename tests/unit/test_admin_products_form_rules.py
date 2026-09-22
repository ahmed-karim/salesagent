"""Pure rules behind the product form: ID shape."""

import pytest

from src.admin.blueprints.products import _PRODUCT_ID_PATTERN


@pytest.mark.parametrize("product_id", ["homepage_takeover", "prod_3f9a1c2e", "Moments-Display-2026", "a"])
def test_accepted_product_ids(product_id):
    assert _PRODUCT_ID_PATTERN.match(product_id)


@pytest.mark.parametrize("product_id", ["", "homepage takeover", "takeover!", "_leading", "-leading", "x" * 101, "a/b"])
def test_refused_product_ids(product_id):
    assert not _PRODUCT_ID_PATTERN.match(product_id)
