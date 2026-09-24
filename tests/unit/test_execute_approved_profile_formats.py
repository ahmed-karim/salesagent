"""Unit test: approval reconstructs a profile-backed product's formats from the profile.

A product attached to an inventory profile stores its formats on the profile, not on its
own ``format_ids`` column (``Product.effective_format_ids`` is the one accessor that knows
this, and ``get_products`` already advertises the profile's formats). The approval path
rebuilt each ``MediaPackage`` from ``product.format_ids`` directly, so every buy on such a
product was accepted, held for approval, and then refused at approval with
"Product ... has no valid formats - cannot create media buy". The same raw column read
gated creative-format validation at create time and in ``update_media_buy``.

The product below is a real ORM ``Product`` with an empty ``format_ids`` column and an
``InventoryProfile`` carrying two formats. Without the fix ``execute_approved_media_buy``
returns FAILED; with it the adapter receives a package carrying the profile's formats.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.adapters.base import AdapterCreateResult
from src.core.database.models import InventoryProfile, Product
from src.core.database.repositories.creative import CreativeAssignmentRepository
from src.core.tools.media_buy_create import ApprovalOutcome
from tests.factories.principal import PrincipalFactory
from tests.unit.test_execute_approved_status_update import (
    _make_mock_media_buy,
    _make_mock_package,
    _make_mock_tenant,
)

_AGENT = "https://creative.adcontextprotocol.org"
_PROFILE_FORMATS = [
    {"agent_url": _AGENT, "id": "display_300x250_image_1x_2x"},
    {"agent_url": _AGENT, "id": "display_728x90_image_1x_2x"},
]


def _make_profile_backed_product() -> Product:
    """A real ORM Product: empty own ``format_ids``, formats on its inventory profile."""
    pricing_option = MagicMock()
    pricing_option.pricing_model = "CPM"
    pricing_option.rate = Decimal("5.00")
    pricing_option.currency = "USD"
    pricing_option.is_fixed = True
    pricing_option.root = pricing_option
    product = Product(
        tenant_id="tenant_1",
        product_id="prod_1",
        name="In-Game Display",
        description="profile-backed",
        format_ids=[],
        delivery_type="guaranteed",
        inventory_profile_id=7,
    )
    product.inventory_profile = InventoryProfile(
        id=7, tenant_id="tenant_1", name="In-Game Display profile", format_ids=list(_PROFILE_FORMATS)
    )
    product.pricing_options = [pricing_option]
    return product


def test_profile_backed_product_reaches_the_adapter_with_the_profile_formats():
    tenant = _make_mock_tenant()
    media_buy = _make_mock_media_buy()
    db_package = _make_mock_package()
    product = _make_profile_backed_product()
    assert product.format_ids == [] and product.effective_format_ids == _PROFILE_FORMATS

    adapter_response = AdapterCreateResult(media_buy_id="mb_test_001", packages=[])
    mock_adapter = MagicMock()
    mock_adapter.orders_manager = None

    mock_session_1 = MagicMock()
    mock_session_1.scalars = MagicMock(
        side_effect=[
            MagicMock(first=MagicMock(return_value=tenant)),
            MagicMock(first=MagicMock(return_value=media_buy)),
            MagicMock(all=MagicMock(return_value=[db_package])),
            MagicMock(first=MagicMock(return_value=product)),
        ]
    )
    mock_session_2 = MagicMock()
    mock_session_2.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    def _uow(session, media_buys):
        uow = MagicMock()
        uow.__enter__ = MagicMock(return_value=uow)
        uow.__exit__ = MagicMock(return_value=None)
        uow.session = session
        uow.media_buys = media_buys
        return uow

    repo_plids = MagicMock()
    repo_plids.get_packages.return_value = [db_package]
    repo_3 = MagicMock()
    repo_3.get_by_id.return_value = media_buy
    uow_iter = iter(
        [
            _uow(mock_session_1, MagicMock()),
            _uow(MagicMock(), repo_plids),
            _uow(mock_session_2, MagicMock()),
            _uow(MagicMock(), repo_3),
        ]
    )

    adapter_call = MagicMock(return_value=adapter_response)
    with (
        patch("src.core.database.repositories.MediaBuyUoW", side_effect=lambda _: next(uow_iter)),
        patch(
            "src.core.config_loader.get_tenant_by_id", return_value={"tenant_id": "tenant_1", "adapter_type": "mock"}
        ),
        patch(
            "src.core.tools.media_buy_create.identity_of",
            return_value=PrincipalFactory.make_identity(principal_id="principal_1", tenant_id="tenant_1"),
        ),
        patch("src.core.tools.media_buy_create._execute_adapter_media_buy_creation", adapter_call),
        patch("src.core.tools.media_buy_create._validate_creatives_before_adapter_call"),
        patch("src.core.helpers.adapter_helpers.get_adapter", return_value=mock_adapter),
        patch.object(CreativeAssignmentRepository, "unapproved_creative_ids", return_value=[]),
    ):
        from src.core.tools.media_buy_create import execute_approved_media_buy

        result = execute_approved_media_buy(
            "mb_test_001", "tenant_1", approved_by="approver@example.com", approved_at=datetime.now(UTC)
        )

    assert result.outcome is ApprovalOutcome.EXECUTED, f"approval refused a profile-backed product: {result}"
    packages = adapter_call.call_args.kwargs.get("packages") or adapter_call.call_args.args[1]
    assert [(str(f.agent_url).rstrip("/"), f.id) for f in packages[0].format_ids] == [
        (_AGENT, f["id"]) for f in _PROFILE_FORMATS
    ]
