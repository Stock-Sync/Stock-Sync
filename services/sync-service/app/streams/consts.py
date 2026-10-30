"""Redis Streams constants and helpers shared by the consumer and flusher."""

STREAM_KEY = "stocksync:events"
CONSUMER_GROUP = "sync-service"
CONSUMER_NAME = "sync-service-1"

# Dead-letter stream for events that exhausted their retries.
DEAD_STREAM_KEY = "stocksync:dead"

# Redis hash holding pending ML quantity updates:
#   field  = "{tenant_id}:{ml_item_id}"
#   value  = json {tenant_id, ml_item_id, sku_id}
PENDING_STOCK_KEY = "pending:stock"

EVENT_STOCK_ADJUST = "stock_adjust"
EVENT_ITEMS_CHANGED = "items_changed"
EVENT_ORDER_CREATED = "order_created"

KNOWN_EVENT_TYPES = {
    EVENT_STOCK_ADJUST,
    EVENT_ITEMS_CHANGED,
    EVENT_ORDER_CREATED,
}
