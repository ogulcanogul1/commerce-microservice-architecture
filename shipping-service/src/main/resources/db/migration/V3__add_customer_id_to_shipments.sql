ALTER TABLE shipments ADD COLUMN customer_id UUID;
CREATE INDEX idx_shipments_customer_id ON shipments (customer_id);
