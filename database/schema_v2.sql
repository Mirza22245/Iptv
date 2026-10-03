-- Lydia Core v2
-- Multi-tenant clinic database with RLS, RBAC context, booking overlap protection,
-- and immutable audit logs.
--
-- IMPORTANT:
-- The application database role must NOT be a PostgreSQL superuser and should
-- not own these tables, otherwise RLS can be bypassed.

BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS clinics (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('customer', 'staff', 'admin', 'superadmin')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (clinic_id, id),
    UNIQUE (email)
);
CREATE INDEX IF NOT EXISTS idx_users_clinic_role ON users (clinic_id, role);

CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    user_id BIGINT UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (clinic_id, id)
);
CREATE INDEX IF NOT EXISTS idx_customers_clinic ON customers (clinic_id);

CREATE TABLE IF NOT EXISTS staff (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    display_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (clinic_id, id)
);
CREATE INDEX IF NOT EXISTS idx_staff_clinic_active ON staff (clinic_id, is_active);

CREATE TABLE IF NOT EXISTS services (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (clinic_id, id)
);
CREATE INDEX IF NOT EXISTS idx_services_clinic_active ON services (clinic_id, is_active);

CREATE TABLE IF NOT EXISTS bookings (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL,
    service_id BIGINT NOT NULL,
    staff_id BIGINT NOT NULL,
    slot_range TSTZRANGE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_booking_customer_same_clinic FOREIGN KEY (clinic_id, customer_id)
        REFERENCES customers (clinic_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_booking_service_same_clinic FOREIGN KEY (clinic_id, service_id)
        REFERENCES services (clinic_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_booking_staff_same_clinic FOREIGN KEY (clinic_id, staff_id)
        REFERENCES staff (clinic_id, id) ON DELETE RESTRICT,
    CONSTRAINT booking_slot_nonempty CHECK (NOT isempty(slot_range)),
    EXCLUDE USING gist (staff_id WITH =, slot_range WITH &&) WHERE (status <> 'cancelled')
);
CREATE INDEX IF NOT EXISTS idx_bookings_clinic_start ON bookings (clinic_id, lower(slot_range));
CREATE INDEX IF NOT EXISTS idx_bookings_customer ON bookings (clinic_id, customer_id, lower(slot_range));
CREATE INDEX IF NOT EXISTS idx_bookings_staff ON bookings (clinic_id, staff_id, lower(slot_range));

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(100) NOT NULL,
    target_id BIGINT NOT NULL,
    new_values JSONB,
    performed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    performed_by_user_id BIGINT,
    request_id UUID
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_clinic_time ON audit_logs (clinic_id, performed_at DESC);

CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit logs are immutable: UPDATE and DELETE are forbidden.' USING ERRCODE = '42501';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_prevent_audit_update ON audit_logs;
CREATE TRIGGER trg_prevent_audit_update BEFORE UPDATE ON audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
DROP TRIGGER IF EXISTS trg_prevent_audit_delete ON audit_logs;
CREATE TRIGGER trg_prevent_audit_delete BEFORE DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

CREATE OR REPLACE FUNCTION lydia_context_bigint(setting_name TEXT)
RETURNS BIGINT LANGUAGE SQL STABLE AS $$
    SELECT NULLIF(current_setting(setting_name, true), '')::BIGINT;
$$;
CREATE OR REPLACE FUNCTION lydia_context_text(setting_name TEXT)
RETURNS TEXT LANGUAGE SQL STABLE AS $$
    SELECT NULLIF(current_setting(setting_name, true), '');
$$;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers FORCE ROW LEVEL SECURITY;
ALTER TABLE staff ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff FORCE ROW LEVEL SECURITY;
ALTER TABLE services ENABLE ROW LEVEL SECURITY;
ALTER TABLE services FORCE ROW LEVEL SECURITY;
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_tenant_isolation ON users;
CREATE POLICY users_tenant_isolation ON users
FOR ALL
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND (
        id = lydia_context_bigint('lydia.current_user_id')
        OR lydia_context_text('lydia.current_role') IN ('staff', 'admin', 'superadmin')
    )
)
WITH CHECK (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
);

DROP POLICY IF EXISTS customers_tenant_isolation ON customers;
CREATE POLICY customers_tenant_isolation ON customers
FOR ALL
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND (
        user_id = lydia_context_bigint('lydia.current_user_id')
        OR lydia_context_text('lydia.current_role') IN ('staff', 'admin', 'superadmin')
    )
)
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id'));

DROP POLICY IF EXISTS staff_tenant_isolation ON staff;
CREATE POLICY staff_tenant_isolation ON staff FOR ALL
USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id'))
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id'));

DROP POLICY IF EXISTS services_tenant_isolation ON services;
CREATE POLICY services_tenant_isolation ON services FOR ALL
USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id'))
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id'));

DROP POLICY IF EXISTS bookings_tenant_isolation ON bookings;
CREATE POLICY bookings_tenant_isolation ON bookings FOR SELECT
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND (
        customer_id IN (SELECT c.id FROM customers c WHERE c.user_id = lydia_context_bigint('lydia.current_user_id'))
        OR staff_id IN (SELECT s.id FROM staff s WHERE s.user_id = lydia_context_bigint('lydia.current_user_id'))
        OR lydia_context_text('lydia.current_role') IN ('admin', 'superadmin')
    )
);

DROP POLICY IF EXISTS bookings_customer_insert ON bookings;
CREATE POLICY bookings_customer_insert ON bookings FOR INSERT
WITH CHECK (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND (
        customer_id IN (SELECT c.id FROM customers c WHERE c.user_id = lydia_context_bigint('lydia.current_user_id'))
        OR lydia_context_text('lydia.current_role') IN ('staff', 'admin', 'superadmin')
    )
);

DROP POLICY IF EXISTS bookings_update ON bookings;
CREATE POLICY bookings_update ON bookings FOR UPDATE
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND (
        customer_id IN (SELECT c.id FROM customers c WHERE c.user_id = lydia_context_bigint('lydia.current_user_id'))
        OR staff_id IN (SELECT s.id FROM staff s WHERE s.user_id = lydia_context_bigint('lydia.current_user_id'))
        OR lydia_context_text('lydia.current_role') IN ('admin', 'superadmin')
    )
)
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id'));

DROP POLICY IF EXISTS bookings_delete ON bookings;
CREATE POLICY bookings_delete ON bookings FOR DELETE
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND lydia_context_text('lydia.current_role') IN ('admin', 'superadmin')
);

DROP POLICY IF EXISTS audit_insert ON audit_logs;
CREATE POLICY audit_insert ON audit_logs FOR INSERT
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id'));
DROP POLICY IF EXISTS audit_select ON audit_logs;
CREATE POLICY audit_select ON audit_logs FOR SELECT
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND lydia_context_text('lydia.current_role') IN ('admin', 'superadmin')
);

COMMIT;
