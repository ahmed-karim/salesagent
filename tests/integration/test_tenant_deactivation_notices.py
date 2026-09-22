"""While a sales agent is deactivated the admin shows a banner, and each switch posts to Slack."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.database.models import Tenant
from tests.factories import TenantFactory
from tests.harness._base import IntegrationEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

WEBHOOK = "https://hooks.slack.example/T000/B000/xyz"


def test_admin_banner_while_deactivated(authenticated_admin_session):
    with IntegrationEnv(tenant_id="dz_banner"):
        TenantFactory(tenant_id="dz_banner", is_active=False)

        body = authenticated_admin_session.get("/tenant/dz_banner/settings").data.decode()
        assert "This sales agent is deactivated." in body

        TenantFactory(tenant_id="dz_banner_on")
        body = authenticated_admin_session.get("/tenant/dz_banner_on/settings").data.decode()
        assert "This sales agent is deactivated." not in body


def _delivered(sent: list):
    """The HTTP seam, answering "delivered": the real deliver_webhook_with_retry around it then
    commits its delivery record through its own session, which expires and detaches rows the
    admin handler's session still holds."""

    def deliver(url, payload, **kwargs):
        sent.append(payload["text"])
        return SimpleNamespace(kind="delivered", attempts=1, http_status=200)

    return deliver


def test_deactivate_and_reactivate_post_to_slack(authenticated_admin_session):
    client = authenticated_admin_session
    with IntegrationEnv(tenant_id="dz_slack") as env:
        TenantFactory(tenant_id="dz_slack", name="Slack Publisher", slack_webhook_url=WEBHOOK)
        sent: list[str] = []

        with patch("src.core.webhook_delivery.deliver_webhook", side_effect=_delivered(sent)):
            client.post("/tenant/dz_slack/deactivate", data={"confirm_name": "Slack Publisher"})
            with client.session_transaction() as sess:
                flashes = [message for _, message in sess.get("_flashes", [])]
            client.post("/admin/tenant/dz_slack/reactivate")

        assert "Slack Publisher: sales agent deactivated" in sent[0]
        assert "Slack Publisher: sales agent reactivated" in sent[1]
        # The handler finished normally after the notice (the row was not left detached).
        assert flashes == ["Sales agent 'Slack Publisher' has been deactivated. All data is preserved."]
        session = env.get_session()
        session.expire_all()
        assert session.get(Tenant, "dz_slack").is_active is True


def test_deactivated_host_gets_the_notice_not_domain_not_configured(integration_db):
    from starlette.testclient import TestClient

    from src.app import app

    with IntegrationEnv(tenant_id="dz_land"):
        TenantFactory(
            tenant_id="dz_land", name="Landing Publisher", virtual_host="landing-test.example.com", is_active=False
        )

        body = TestClient(app).get("/", headers={"host": "landing-test.example.com"}).text
        assert "Landing Publisher is not currently accepting requests." in body
        assert "is not configured" not in body


def test_a_slack_failure_does_not_undo_the_switch(authenticated_admin_session):
    with IntegrationEnv(tenant_id="dz_slack_err") as env:
        TenantFactory(tenant_id="dz_slack_err", name="Flaky Publisher", slack_webhook_url=WEBHOOK)

        with patch("src.admin.blueprints.tenants.SlackNotifier") as notifier:
            notifier.return_value.send_message.side_effect = RuntimeError("slack down")
            resp = authenticated_admin_session.post(
                "/tenant/dz_slack_err/deactivate", data={"confirm_name": "Flaky Publisher"}
            )

        assert resp.status_code == 302
        session = env.get_session()
        session.expire_all()
        assert session.get(Tenant, "dz_slack_err").is_active is False
