"""Longitude patch 07: the A2A agent card carries the publisher's name.

The static card only knows the software's name ("Prebid Sales Agent"). When the Host routes
to a tenant, the served card carries that tenant's name and a description built from it; an
unrouted Host or a failed lookup serves the static card, never a 500.
"""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.core.agent_identity import AgentIdentity
from src.core.domain_routing import RoutingResult

TENANT = {"tenant_id": "default", "name": "Unwind Media", "subdomain": "default", "virtual_host": "agent.example.com"}
CARD_PATHS = ["/.well-known/agent-card.json", "/.well-known/agent.json", "/agent.json"]
IDENTITY = AgentIdentity(origin="https://agent.example.com", endpoints={"a2a": "https://agent.example.com/a2a"})
ROUTED = RoutingResult("custom_domain", TENANT, "agent.example.com")
UNROUTED = RoutingResult("custom_domain", None, "unknown.example.net")


@pytest.fixture
def client():
    from src.app import app

    return TestClient(app)


def test_card_carries_the_tenant_name_for_a_routed_host(client):
    with (
        patch("src.app.route_landing_page", return_value=ROUTED),
        patch("src.app.agent_identity_for_tenant_id", return_value=IDENTITY),
    ):
        card = client.get(CARD_PATHS[0], headers={"Host": "agent.example.com"}).json()
    assert card["name"] == "Unwind Media"
    assert "Unwind Media" in card["description"]
    assert card["supportedInterfaces"][0]["url"] == "https://agent.example.com/a2a"
    assert len(card["skills"]) > 0  # everything else is the static card


def test_every_declared_card_path_serves_the_same_branded_card(client):
    with (
        patch("src.app.route_landing_page", return_value=ROUTED),
        patch("src.app.agent_identity_for_tenant_id", return_value=IDENTITY),
    ):
        bodies = [client.get(path, headers={"Host": "agent.example.com"}).json() for path in CARD_PATHS]
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["name"] == "Unwind Media"


def test_card_keeps_the_static_name_for_an_unrouted_host(client):
    with patch("src.app.route_landing_page", return_value=UNROUTED):
        card = client.get(CARD_PATHS[0], headers={"Host": "unknown.example.net"}).json()
    assert card["name"] == "Prebid Sales Agent"


def test_card_survives_a_failed_tenant_lookup(client):
    with (
        patch("src.app._canonical_a2a_url", return_value=None),
        patch("src.app.route_landing_page", side_effect=RuntimeError("database unreachable")),
    ):
        response = client.get(CARD_PATHS[0])
    assert response.status_code == 200
    assert response.json()["name"] == "Prebid Sales Agent"
