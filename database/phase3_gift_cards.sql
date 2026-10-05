-- Lydia Phase 3: gift cards, atomic transactions and tenant isolation.
-- Run after schema_v2.sql, phase2_clinical.sql and phase3_business.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS gift_cards (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    code VARCHAR(64) NOT NULL,
    initial_amount NUMERIC(12,2) NOT NULL CHECK (initial_amount > 0),
    balance NUMERIC(12,2) NOT NULL CHECK (balance >= 0),
    status VARCHAR(32) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','depleted','expired','refunded')),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (clinic_id, id),
    UNIQUE (clinic_id, code)
);

CREATE TABLE IF NOT EXISTS gift_card_transactions (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    gift_card_id BIGINT NOT NULL,
    type VARCHAR(32) NOT NULL CHECK (type IN ('purchase','redeem','refund','expire')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    reference_id BIGINT,
    created_by_user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (clinic_id, gift_card_id) REFERENCES gift_cards(clinic_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users(clinic_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_gift_cards_clinic_code ON gift_cards(clinic_id, code);
CREATE INDEX IF NOT EXISTS idx_gift_card_transactions_lookup ON gift_card_transactions(clinic_id, gift_card_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gift_card_transaction_reference
    ON gift_card_transactions(clinic_id, type, reference_id)
    WHERE reference_id IS NOT NULL AND type IN ('redeem','refund');

ALTER TABLE gift_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE gift_cards FORCE ROW LEVEL SECURITY;
ALTER TABLE gift_card_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gift_card_transactions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS gift_cards_tenant ON gift_cards;
CREATE POLICY gift_cards_tenant ON gift_cards FOR ALL
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')
)
WITH CHECK (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')
);

DROP POLICY IF EXISTS gift_card_transactions_tenant ON gift_card_transactions;
CREATE POLICY gift_card_transactions_tenant ON gift_card_transactions FOR ALL
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')
)
WITH CHECK (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')
);

COMMIT;
