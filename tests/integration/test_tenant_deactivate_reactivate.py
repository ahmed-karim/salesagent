"""A super admin deactivates a sales agent from Settings > Danger Zone and reactivates it there.

Real database, real Flask app, real form POSTs. Before this, the Danger Zone was hidden in
single-tenant mode, deactivating signed the clicker out, and reactivate_tenant had no button
and refused a super admin who signed in through tenant SSO (session role "tenant_admin").
"""

import pytest
from sqlalchemy import select

from src.core.config import load_settings
from src.core.database.models import AuditLog, Tenant
from tests.factories import TenantFactory
from tests.harness._base import IntegrationEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def _tenant_row(env, tenant_id: str) -> Tenant:
    session = env.get_session()
    session.expire_all()  # the form handler committed through its own session
    return session.get(Tenant, tenant_id)


def _as_sso_user(client, email: str = "test@example.com") -> None:
    """A user as tenant SSO leaves the session: a tenant role, no test user.

    The default is the fixture's super admin (in super_admin_emails).
    """
    with client.session_transaction() as sess:
        for key in ("test_user", "test_user_role", "test_user_name", "is_super_admin", "admin_email"):
            sess.pop(key, None)
        sess["role"] = "tenant_admin"
        sess["user"] = email


class TestDeactivateReactivate:
    def test_super_admin_deactivates_stays_signed_in_and_reactivates(self, authenticated_admin_session):
        client = authenticated_admin_session
        with IntegrationEnv(tenant_id="dz_round") as env:
            TenantFactory(tenant_id="dz_round", name="Round Trip Publisher")

            page = client.get("/tenant/dz_round/settings").data.decode()
            assert 'data-section="danger-zone"' in page
            assert "Deactivate Sales Agent" in page

            resp = client.post("/tenant/dz_round/deactivate", data={"confirm_name": "Round Trip Publisher"})
            assert resp.status_code == 302
            assert resp.headers["Location"].endswith("/settings/danger-zone")
            assert _tenant_row(env, "dz_round").is_active is False

            # Still signed in: the settings page renders, offering Reactivate instead of Deactivate.
            page = client.get("/tenant/dz_round/settings").data.decode()
            assert "Reactivate Sales Agent" in page
            assert 'id="deactivate-form"' not in page

            resp = client.post("/admin/tenant/dz_round/reactivate")
            assert resp.status_code == 302
            assert resp.headers["Location"].endswith("/settings/danger-zone")
            assert _tenant_row(env, "dz_round").is_active is True

    def test_sso_super_admin_can_reactivate(self, authenticated_admin_session):
        client = authenticated_admin_session
        with IntegrationEnv(tenant_id="dz_sso") as env:
            TenantFactory(tenant_id="dz_sso", is_active=False)
            _as_sso_user(client)

            resp = client.post("/admin/tenant/dz_sso/reactivate")
            assert resp.status_code == 302
            assert _tenant_row(env, "dz_sso").is_active is True

    def test_super_admin_emails_alone_can_reactivate(self, authenticated_admin_session, monkeypatch):
        """A single-tenant deployment names who may reactivate in SUPER_ADMIN_EMAILS.

        Upstream documents SUPER_ADMIN_* as legacy. This address is in the environment only (the
        database fixture grants test@example.com), so the test fails if the variable stops
        granting super admin; a tenant admin outside it is refused.
        """
        client = authenticated_admin_session
        monkeypatch.setenv("SUPER_ADMIN_EMAILS", "ops@publisher.example")
        load_settings()
        with IntegrationEnv(tenant_id="dz_env") as env:
            TenantFactory(tenant_id="dz_env", is_active=False)

            _as_sso_user(client, "member@publisher.example")
            client.post("/admin/tenant/dz_env/reactivate")
            assert _tenant_row(env, "dz_env").is_active is False

            _as_sso_user(client, "ops@publisher.example")
            client.post("/admin/tenant/dz_env/reactivate")
            assert _tenant_row(env, "dz_env").is_active is True

    def test_wrong_name_does_not_deactivate(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="dz_name") as env:
            TenantFactory(tenant_id="dz_name", name="Named Publisher")

            resp = authenticated_admin_session.post("/tenant/dz_name/deactivate", data={"confirm_name": "nope"})
            assert resp.status_code == 302
            assert _tenant_row(env, "dz_name").is_active is True

    def test_both_switches_write_an_audit_row(self, authenticated_admin_session):
        """prebid/salesagent#2135: the audit row comes from @log_admin_action, not log_security_event."""
        client = authenticated_admin_session
        with IntegrationEnv(tenant_id="dz_audit") as env:
            TenantFactory(tenant_id="dz_audit", name="Audited Publisher")

            client.post("/tenant/dz_audit/deactivate", data={"confirm_name": "Audited Publisher"})
            client.post("/admin/tenant/dz_audit/reactivate")

            session = env.get_session()
            session.expire_all()
            operations = session.scalars(
                select(AuditLog.operation).filter_by(tenant_id="dz_audit", success=True).order_by(AuditLog.timestamp)
            ).all()
            assert operations == ["AdminUI.deactivate_tenant", "AdminUI.reactivate_tenant"]
