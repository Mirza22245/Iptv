-- Lydia Core Phase 3: POS, payments, inventory, reports and external integration metadata.
-- Idempotent migration; run after schema_v2.sql and phase2_clinical.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    vat_rate NUMERIC(5,2) NOT NULL DEFAULT 25 CHECK (vat_rate >= 0 AND vat_rate <= 100),
    stock_quantity NUMERIC(12,3) NOT NULL DEFAULT 0,
    reorder_level NUMERIC(12,3) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (clinic_id, id),
    UNIQUE (clinic_id, sku)
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL,
    movement_type VARCHAR(30) NOT NULL CHECK (movement_type IN ('purchase','sale','adjustment','return','waste')),
    quantity NUMERIC(12,3) NOT NULL CHECK (quantity <> 0),
    unit_cost NUMERIC(12,2),
    reference_type VARCHAR(50),
    reference_id BIGINT,
    note TEXT,
    created_by_user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (clinic_id, product_id) REFERENCES products(clinic_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users(clinic_id, id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_inventory_movements_product ON inventory_movements(clinic_id, product_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sales (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    customer_id BIGINT,
    booking_id BIGINT,
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','paid','refunded','void')),
    subtotal NUMERIC(12,2) NOT NULL DEFAULT 0,
    vat_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    total NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency CHAR(3) NOT NULL DEFAULT 'SEK',
    created_by_user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ,
    FOREIGN KEY (clinic_id, customer_id) REFERENCES customers(clinic_id, id) ON DELETE SET NULL,
    FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users(clinic_id, id) ON DELETE RESTRICT,
    UNIQUE (clinic_id, id)
);
ALTER TABLE sales ADD COLUMN IF NOT EXISTS receipt_number BIGINT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_clinic_receipt_number
    ON sales(clinic_id, receipt_number)
    WHERE receipt_number IS NOT NULL;

CREATE OR REPLACE FUNCTION assign_receipt_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.receipt_number IS NULL AND NEW.status = 'paid' THEN
        NEW.receipt_number := (
            SELECT COALESCE(MAX(receipt_number), 0) + 1
            FROM sales
            WHERE clinic_id = NEW.clinic_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_assign_receipt_number ON sales;
CREATE TRIGGER trg_assign_receipt_number
BEFORE INSERT OR UPDATE OF status ON sales
FOR EACH ROW EXECUTE FUNCTION assign_receipt_number();

ALTER TABLE sales ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);
ALTER TABLE sales ADD COLUMN IF NOT EXISTS idempotency_fingerprint CHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_clinic_idempotency_key
    ON sales(clinic_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sales_clinic_time ON sales(clinic_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sale_items (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    sale_id BIGINT NOT NULL,
    product_id BIGINT,
    service_id BIGINT,
    description VARCHAR(255) NOT NULL,
    quantity NUMERIC(12,3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    vat_rate NUMERIC(5,2) NOT NULL DEFAULT 25,
    line_total NUMERIC(12,2) NOT NULL CHECK (line_total >= 0),
    FOREIGN KEY (clinic_id, sale_id) REFERENCES sales(clinic_id, id) ON DELETE CASCADE,
    FOREIGN KEY (clinic_id, product_id) REFERENCES products(clinic_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (clinic_id, service_id) REFERENCES services(clinic_id, id) ON DELETE RESTRICT,
    CHECK ((product_id IS NOT NULL) OR (service_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    sale_id BIGINT NOT NULL,
    method VARCHAR(30) NOT NULL CHECK (method IN ('card','swish','cash','invoice','other')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    external_reference VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'completed' CHECK (status IN ('pending','completed','failed','refunded')),
    created_by_user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (clinic_id, sale_id) REFERENCES sales(clinic_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users(clinic_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS integration_connections (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL CHECK (provider IN ('bokadirekt','meridiq','stripe','swish','other')),
    status VARCHAR(20) NOT NULL DEFAULT 'disabled' CHECK (status IN ('disabled','configured','active','error')),
    external_account_id VARCHAR(255),
    settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_sync_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (clinic_id, provider)
);

CREATE TABLE IF NOT EXISTS integration_events (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('in','out')),
    event_type VARCHAR(100) NOT NULL,
    external_id VARCHAR(255),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'received',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_integration_events_lookup ON integration_events(clinic_id, provider, created_at DESC);

CREATE TABLE IF NOT EXISTS report_snapshots (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    report_type VARCHAR(50) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE products FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_movements FORCE ROW LEVEL SECURITY;
ALTER TABLE sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales FORCE ROW LEVEL SECURITY;
ALTER TABLE sale_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale_items FORCE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments FORCE ROW LEVEL SECURITY;
ALTER TABLE integration_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_connections FORCE ROW LEVEL SECURITY;
ALTER TABLE integration_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_events FORCE ROW LEVEL SECURITY;
ALTER TABLE report_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_snapshots FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS products_tenant ON products;
CREATE POLICY products_tenant ON products FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));
DROP POLICY IF EXISTS inventory_tenant ON inventory_movements;
CREATE POLICY inventory_tenant ON inventory_movements FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));
DROP POLICY IF EXISTS sales_tenant ON sales;
CREATE POLICY sales_tenant ON sales FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));
DROP POLICY IF EXISTS sale_items_tenant ON sale_items;
CREATE POLICY sale_items_tenant ON sale_items FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));
DROP POLICY IF EXISTS payments_tenant ON payments;
CREATE POLICY payments_tenant ON payments FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));
DROP POLICY IF EXISTS integrations_tenant ON integration_connections;
CREATE POLICY integrations_tenant ON integration_connections FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('admin','superadmin'));
DROP POLICY IF EXISTS integration_events_tenant ON integration_events;
CREATE POLICY integration_events_tenant ON integration_events FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('admin','superadmin'));
DROP POLICY IF EXISTS reports_tenant ON report_snapshots;
CREATE POLICY reports_tenant ON report_snapshots FOR ALL USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('admin','superadmin')) WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('admin','superadmin'));

COMMIT;
