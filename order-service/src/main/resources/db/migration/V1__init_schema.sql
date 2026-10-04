-- ==============================================================================
-- Order Service Database Schema (order_db)
-- Tüm ID'ler UUID standardında tutulmaktadır (gen_random_uuid()).
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Siparişler Tablosu (Order Aggregate Root)
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(50) NOT NULL UNIQUE,
    customer_id UUID NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'PENDING' CHECK (status IN (
        'PENDING', 
        'INVENTORY_RESERVED', 
        'PAYMENT_AUTHORIZED', 
        'SHIPPING_CREATED', 
        'CONFIRMED', 
        'INVENTORY_FAILED', 
        'PAYMENT_FAILED', 
        'SHIPPING_FAILED', 
        'CANCELLED'
    )),
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'TRY',
    shipping_address JSONB NOT NULL,
    failure_reason TEXT,
    correlation_id UUID NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_order_number ON orders(order_number);
CREATE INDEX IF NOT EXISTS idx_orders_correlation_id ON orders(correlation_id);

-- 2. Sipariş Kalemleri Tablosu (Order Items)
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku VARCHAR(50) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    quantity INT NOT NULL CHECK (quantity > 0),
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_sku ON order_items(sku);

-- 3. Saga Durum İzleme Tablosu (Order Saga Tracking)
CREATE TABLE IF NOT EXISTS order_saga_states (
    order_id UUID PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
    current_step VARCHAR(50) NOT NULL,
    inventory_reserved_at TIMESTAMP WITH TIME ZONE,
    payment_authorized_at TIMESTAMP WITH TIME ZONE,
    shipping_created_at TIMESTAMP WITH TIME ZONE,
    failure_step VARCHAR(50),
    failure_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Transactional Outbox Tablosu
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PUBLISHED', 'FAILED')),
    retry_count INT NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_order_outbox_status_created ON outbox_events(status, created_at);

-- 5. Tüketici Idempotency (Yinelenen Olayları Tekilleştirme) Tablosu
CREATE TABLE IF NOT EXISTS processed_events (
    consumer_group VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_group, event_id)
);

-- Otomatik updated_at Tetikleyicisi
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orders_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_saga_updated_at
BEFORE UPDATE ON order_saga_states
FOR EACH ROW EXECUTE FUNCTION update_timestamp();
