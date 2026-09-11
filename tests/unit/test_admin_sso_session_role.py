"""SSO login completion must set session["role"] (Longitude divergence 14).

policy.update (src/admin/blueprints/policy.py) and the tenant-scoped checks key on
session["role"]. Before the fix only test-auth and the super-admin branch set it, so every
tenant admin who logged in through Google or OIDC got 403 saving policy settings.
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def app():
    from src.admin.app import create_app

    app = create_app({"TESTING": True})
    app.config["SECRET_KEY"] = "test_secret"
    return app


@pytest.mark.parametrize(
    ("is_admin", "expected_role"),
    [(True, "tenant_admin"), (False, "tenant_user")],
)
def test_select_tenant_sets_session_role(app, is_admin, expected_role):
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = "ops@example.com"
            sess["available_tenants"] = [
                {"tenant_id": "default", "name": "Publisher", "subdomain": "default", "is_admin": is_admin}
            ]

        with patch("src.admin.domain_access.ensure_user_in_tenant"):
            response = client.post("/auth/select-tenant", data={"tenant_id": "default"})

        assert response.status_code == 302
        with client.session_transaction() as sess:
            assert sess["tenant_id"] == "default"
            assert sess["role"] == expected_role
            assert sess["is_tenant_admin"] is is_admin
