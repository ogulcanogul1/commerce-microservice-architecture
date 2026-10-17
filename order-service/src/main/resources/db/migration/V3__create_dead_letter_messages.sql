CREATE TABLE dead_letter_messages (
    id UUID PRIMARY KEY,
    original_topic VARCHAR(150) NOT NULL,
    original_key VARCHAR(255),
    payload TEXT NOT NULL,
    exception_message TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    replayed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_dead_letter_status ON dead_letter_messages (status);
CREATE INDEX idx_dead_letter_original_topic ON dead_letter_messages (original_topic);
CREATE INDEX idx_dead_letter_created_at ON dead_letter_messages (created_at);
