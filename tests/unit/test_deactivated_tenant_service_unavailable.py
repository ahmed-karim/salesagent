"""A request that names a deactivated tenant is refused with SERVICE_UNAVAILABLE, on every transport.

Deactivated tenants (``Tenant.is_active`` false) are invisible to the tenant lookups, so the
buyer used to be told its credential was invalid. ``_resolve_identity()``, the one boundary
every MCP, A2A and REST request passes through, now raises ``AdCPServiceUnavailableError``
(503, recovery ``transient``, ``retry_after`` set) before any credential is checked.

Spec: AdCP 3.1.1 ``building/by-layer/L3/error-handling.mdx`` § Standard Error Codes
(``SERVICE_UNAVAILABLE`` = transient, "retry with exponential backoff").
"""

from unittest.mock import patch

import pytest

from src.core.exceptions import AdCPServiceUnavailableError
from src.core.resolved_identity import _resolve_identity
from src.core.tenant_context import TenantContext
from tests.helpers.credentials import credential_headers

ACTIVE = TenantContext(tenant_id="pub", name="Unwind Media")


def _detect(active: str | None, any_state: str | None):
    """_detect_tenant stand-in: what the active-only and the any-state lookups find."""
    return lambda headers, *, active_only=True: active if active_only else any_state


class TestDeactivatedTenant:
    @patch("src.core.config_loader.is_deactivated_tenant", return_value=True)
    @patch("src.core.resolved_identity._detect_tenant", side_effect=_detect(None, "pub"))
    def test_discovery_request_is_refused(self, _detect_tenant, _deactivated):
        with pytest.raises(AdCPServiceUnavailableError) as exc_info:
            _resolve_identity({"host": "agent.example.com"}, require_valid_token=False)
        assert exc_info.value.error_code == "SERVICE_UNAVAILABLE"
        assert exc_info.value.retry_after == 300

    @patch("src.core.auth_utils.get_principal_from_token")
    @patch("src.core.config_loader.is_deactivated_tenant", return_value=True)
    @patch("src.core.resolved_identity._detect_tenant", side_effect=_detect(None, "pub"))
    def test_refused_before_the_credential_is_checked(self, _detect_tenant, _deactivated, principal_lookup):
        with pytest.raises(AdCPServiceUnavailableError):
            _resolve_identity(
                {**credential_headers(token="tok"), "host": "agent.example.com"}, require_valid_token=True
            )
        principal_lookup.assert_not_called()

    @patch("src.core.config_loader.is_deactivated_tenant")
    @patch("src.core.resolved_identity._detect_tenant", side_effect=_detect("pub", "pub"))
    def test_active_tenant_resolves_without_the_second_lookup(self, _detect_tenant, deactivated):
        with patch("src.core.resolved_identity.TenantContext.load", return_value=ACTIVE):
            identity = _resolve_identity({"host": "agent.example.com"}, require_valid_token=False)
        assert identity.tenant is ACTIVE
        deactivated.assert_not_called()

    @patch("src.core.config_loader.is_deactivated_tenant", return_value=False)
    @patch("src.core.resolved_identity._detect_tenant", side_effect=_detect(None, "made-up-hint"))
    def test_unknown_tenant_is_unchanged(self, _detect_tenant, _deactivated):
        identity = _resolve_identity({"host": "unrelated.example.net"}, require_valid_token=False)
        assert identity.tenant is None

    @patch("src.core.config_loader.is_deactivated_tenant")
    @patch("src.core.resolved_identity._detect_tenant", side_effect=_detect(None, None))
    def test_no_tenant_named_means_no_lookup(self, _detect_tenant, deactivated):
        assert _resolve_identity({"host": "unrelated.example.net"}, require_valid_token=False).tenant is None
        deactivated.assert_not_called()
