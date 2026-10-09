-- ====================================================================
-- Notification Service - Initial Database Schema (Flyway V1)
-- PostgreSQL DDL for notification_db
-- ====================================================================

-- 1. Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID,
    channel VARCHAR(20) NOT NULL,
    recipient VARCHAR(150) NOT NULL,
    subject VARCHAR(255),
    content TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'SENT',
    event_id UUID NOT NULL,
    error_message TEXT,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_customer_id ON notifications (customer_id);
CREATE INDEX IF NOT EXISTS idx_notifications_event_id ON notifications (event_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications (status);

-- 2. Processed Events Table (Idempotent Consumer Pattern)
CREATE TABLE IF NOT EXISTS processed_events (
    consumer_group VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_group, event_id)
);
