"""Product IDs the seller can choose, duplicate-ID detection, and profile-owned properties.

Product IDs are buyer-visible (``get_products``, every ``create_media_buy`` package) and the
per-tenant primary key, yet the GAM add-product form had no field for one and a reused ID
surfaced as a raw database error.

Real database, real Flask app, real form POSTs; formats are left empty so no creative agent is
contacted. Tenants use the mock adapter for the POST paths (the handler is adapter-neutral) and
Google Ad Manager for the one render assertion that targets the GAM template.
"""

import pytest
from sqlalchemy import select

from src.core.database.models import Product
from tests.factories import AuthorizedPropertyFactory, ProductFactory, TenantFactory
from tests.harness._base import IntegrationEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

DOMAIN = "unwind-test"
TAG = "all_inventory"


def _tenant(tenant_id: str, ad_server: str = "mock"):
    # TenantFactory already gives the tenant a USD currency limit.
    tenant = TenantFactory(tenant_id=tenant_id, ad_server=ad_server)
    AuthorizedPropertyFactory(tenant=tenant, publisher_domain=DOMAIN, tags=[TAG])
    return tenant


def _form(**overrides) -> dict:
    data = {
        "name": "Homepage Takeover",
        "description": "Above-the-fold takeover",
        "formats": "[]",
        "pricing_model_0": "cpm_fixed",
        "currency_0": "USD",
        "rate_0": "10.00",
        "property_mode": "tags",
        "selected_property_tags": f"{DOMAIN}:{TAG}",
    }
    data.update(overrides)
    return data


def _products(env, tenant_id: str) -> list[Product]:
    session = env.get_session()
    session.expire_all()  # the form handler committed through its own session
    return list(session.scalars(select(Product).filter_by(tenant_id=tenant_id).order_by(Product.product_id)))


class TestChosenProductIds:
    def test_a_chosen_product_id_is_saved_verbatim(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="pid_choose") as env:
            _tenant("pid_choose")
            resp = authenticated_admin_session.post(
                "/tenant/pid_choose/products/add", data=_form(product_id="homepage_takeover")
            )
            assert resp.status_code == 302, resp.data[:500]
            assert [p.product_id for p in _products(env, "pid_choose")] == ["homepage_takeover"]

    def test_blank_product_id_still_auto_generates(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="pid_blank") as env:
            _tenant("pid_blank")
            resp = authenticated_admin_session.post("/tenant/pid_blank/products/add", data=_form(product_id=""))
            assert resp.status_code == 302, resp.data[:500]
            (product,) = _products(env, "pid_blank")
            assert product.product_id.startswith("prod_") and len(product.product_id) == 13

    def test_product_id_with_spaces_or_punctuation_is_refused(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="pid_chars") as env:
            _tenant("pid_chars")
            resp = authenticated_admin_session.post(
                "/tenant/pid_chars/products/add", data=_form(product_id="homepage takeover!")
            )
            assert resp.status_code == 200  # form re-rendered, nothing saved
            assert b"letters, numbers, hyphens and underscores" in resp.data
            assert _products(env, "pid_chars") == []


class TestDuplicatesAreFlaggedOnSave:
    def test_reusing_an_existing_product_id_is_refused(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="pid_dupid") as env:
            tenant = _tenant("pid_dupid")
            ProductFactory(tenant=tenant, product_id="homepage_takeover", name="Existing Takeover")
            resp = authenticated_admin_session.post(
                "/tenant/pid_dupid/products/add",
                data=_form(product_id="homepage_takeover", name="A different name"),
            )
            assert resp.status_code == 200
            assert b"already used by" in resp.data
            assert len(_products(env, "pid_dupid")) == 1


class TestGamFormRendering:
    def test_gam_add_form_offers_a_product_id_field(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="pid_gamform"):
            _tenant("pid_gamform", ad_server="google_ad_manager")
            resp = authenticated_admin_session.get("/tenant/pid_gamform/products/add")
            assert resp.status_code == 200
            page = resp.data.decode()
            assert 'name="product_id"' in page
