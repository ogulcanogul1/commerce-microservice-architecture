-- Add destination column to outbox_events for Debezium CDC and EventRouter SMT
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS destination VARCHAR(100);
