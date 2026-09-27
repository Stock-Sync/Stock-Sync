"""
Testes para o sync-service.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.sync import (
    MarketplaceEvent,
    StockUpdateEvent,
    ManualSyncRequest,
    ManualSyncResponse,
    SyncAuditLog,
    SyncStatusResponse,
)


class TestMarketplaceEvent:
    """Testes para o schema MarketplaceEvent."""

    def test_valid_event(self):
        """Testa criação de evento válido."""
        event = MarketplaceEvent(
            event_type="order.created",
            source="mercadolivre",
            user_id="123e4567-e89b-12d3-a456-426614174000",
            external_seller_id="123456",
            order_id="order-123",
            item_id="item-123",
        )
        assert event.event_type == "order.created"
        assert event.source == "mercadolivre"
        assert event.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert event.external_seller_id == "123456"
        assert event.order_id == "order-123"
        assert event.item_id == "item-123"

    def test_event_with_metadata(self):
        """Testa evento com metadata."""
        event = MarketplaceEvent(
            event_type="item.updated",
            source="shopee",
            user_id="123e4567-e89b-12d3-a456-426614174000",
            external_seller_id="789012",
            item_id="item-456",
            metadata={"raw_data": {"quantity": 5}},
        )
        assert event.metadata["raw_data"]["quantity"] == 5

    def test_invalid_event_type(self):
        """Testa que event_type inválido falha."""
        with pytest.raises(ValidationError):
            MarketplaceEvent(
                event_type="invalid.type",
                source="mercadolivre",
                user_id="123e4567-e89b-12d3-a456-426614174000",
                external_seller_id="123456",
            )

    def test_invalid_source(self):
        """Testa que source inválido falha."""
        with pytest.raises(ValidationError):
            MarketplaceEvent(
                event_type="order.created",
                source="amazon",
                user_id="123e4567-e89b-12d3-a456-426614174000",
                external_seller_id="123456",
            )


class TestStockUpdateEvent:
    """Testes para o schema StockUpdateEvent."""

    def test_valid_stock_update(self):
        """Testa criação de evento de atualização de estoque válido."""
        event = StockUpdateEvent(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            platform="mercadolivre",
            sku="SKU-001",
            item_id="MLB123456",
            quantity=10,
            sync_reason="order_created",
            original_event_id=str(uuid.uuid4()),
        )
        assert event.platform == "mercadolivre"
        assert event.sku == "SKU-001"
        assert event.quantity == 10
        assert event.sync_reason == "order_created"
        assert event.model_id == 0  # default

    def test_shopee_with_model_id(self):
        """Testa evento Shopee com model_id."""
        event = StockUpdateEvent(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            platform="shopee",
            sku="SKU-002",
            item_id="12345",
            model_id=67890,
            shop_id=111222,
            quantity=5,
            sync_reason="order_created",
            original_event_id=str(uuid.uuid4()),
        )
        assert event.model_id == 67890
        assert event.shop_id == 111222


class TestManualSyncRequest:
    """Testes para ManualSyncRequest."""

    def test_valid_request(self):
        """Testa request válida."""
        request = ManualSyncRequest(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            platform="mercadolivre",
            sku="SKU-001",
            item_id="MLB123456",
            quantity=20,
        )
        assert request.quantity == 20
        assert request.model_id == 0

    def test_invalid_platform(self):
        """Testa plataforma inválida."""
        with pytest.raises(ValidationError):
            ManualSyncRequest(
                user_id="123e4567-e89b-12d3-a456-426614174000",
                platform="amazon",
                sku="SKU-001",
                item_id="MLB123456",
                quantity=10,
            )


class TestSyncAuditLog:
    """Testes para SyncAuditLog schema."""

    def test_valid_audit_log(self):
        """Testa log de auditoria válido."""
        log = SyncAuditLog(
            id=str(uuid.uuid4()),
            user_id="123e4567-e89b-12d3-a456-426614174000",
            platform="mercadolivre",
            event_type="order.created",
            status="pending",
            original_event_id=str(uuid.uuid4()),
        )
        assert log.status == "pending"
        assert log.platform == "mercadolivre"


class TestSyncStatusResponse:
    """Testes para SyncStatusResponse."""

    def test_valid_response(self):
        """Testa response válida."""
        response = SyncStatusResponse(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            platform="mercadolivre",
            pending_syncs=5,
            last_sync_at=datetime.utcnow(),
        )
        assert response.pending_syncs == 5
        assert response.last_sync_at is not None


# Teste de integração mockado
@patch("app.services.catalog_client.catalog_client.get_mapping_by_external_id")
@patch("app.services.catalog_client.catalog_client.get_stock_quantity")
@patch("app.services.redis_stream.publish_stock_update")
def test_process_order_created(mock_publish, mock_get_stock, mock_get_mapping):
    """Testa processamento de order.created."""
    from app.services.sync_engine import process_marketplace_event

    # Setup mocks
    mock_mapping = MagicMock()
    mock_mapping.sku = "SKU-TEST"
    mock_mapping.external_model_id = 0
    mock_get_mapping.return_value = mock_mapping
    mock_get_stock.return_value = 100
    mock_publish.return_value = "12345-0"

    event_data = {
        "event_id": str(uuid.uuid4()),
        "event_type": "order.created",
        "source": "mercadolivre",
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "external_seller_id": "123456",
        "order_id": "order-123",
        "item_id": "MLB123456",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metadata": {},
    }

    result = process_marketplace_event(event_data)

    assert result is True
    mock_get_mapping.assert_called_once()
    mock_get_stock.assert_called_once()
    mock_publish.assert_called_once()

    # Verifica se o evento publicado tem a quantidade correta (100 - 1 = 99)
    call_args = mock_publish.call_args[0][0]
    assert call_args["quantity"] == 99
    assert call_args["sku"] == "SKU-TEST"
    assert call_args["sync_reason"] == "order_created"


@patch("app.services.catalog_client.catalog_client.get_mapping_by_external_id")
def test_process_event_no_mapping(mock_get_mapping):
    """Testa processamento quando não há mapeamento."""
    from app.services.sync_engine import process_marketplace_event

    mock_get_mapping.return_value = None

    event_data = {
        "event_id": str(uuid.uuid4()),
        "event_type": "order.created",
        "source": "mercadolivre",
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "external_seller_id": "123456",
        "order_id": "order-123",
        "item_id": "MLB123456",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metadata": {},
    }

    result = process_marketplace_event(event_data)

    assert result is False
    mock_get_mapping.assert_called_once()


@patch("app.services.catalog_client.catalog_client.get_mapping_by_external_id")
@patch("app.services.catalog_client.catalog_client.get_stock_quantity")
@patch("app.services.redis_stream.publish_stock_update")
def test_process_order_cancelled(mock_publish, mock_get_stock, mock_get_mapping):
    """Testa processamento de order.cancelled (incrementa estoque)."""
    from app.services.sync_engine import process_marketplace_event

    mock_mapping = MagicMock()
    mock_mapping.sku = "SKU-TEST"
    mock_mapping.external_model_id = 0
    mock_get_mapping.return_value = mock_mapping
    mock_get_stock.return_value = 50
    mock_publish.return_value = "12345-0"

    event_data = {
        "event_id": str(uuid.uuid4()),
        "event_type": "order.cancelled",
        "source": "mercadolivre",
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "external_seller_id": "123456",
        "order_id": "order-123",
        "item_id": "MLB123456",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metadata": {},
    }

    result = process_marketplace_event(event_data)

    assert result is True
    call_args = mock_publish.call_args[0][0]
    # 50 + 1 = 51 (devolução)
    assert call_args["quantity"] == 51
    assert call_args["sync_reason"] == "order_cancelled"