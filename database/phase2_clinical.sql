-- Lydia Core Phase 2: clinical records, journal templates, consents and media metadata.
-- Idempotent migration; safe to run after schema_v2.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS journal_templates (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    structure_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (clinic_id, id)
);

CREATE TABLE IF NOT EXISTS journal_notes (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL,
    author_id BIGINT NOT NULL,
    treatment VARCHAR(255),
    area VARCHAR(255),
    indication TEXT,
    assessment TEXT,
    plan TEXT,
    products_used TEXT,
    dosage VARCHAR(100),
    lot_batch VARCHAR(100),
    result TEXT,
    complications TEXT,
    aftercare TEXT,
    is_signed BOOLEAN NOT NULL DEFAULT FALSE,
    signed_at TIMESTAMPTZ,
    signed_by_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_journal_customer_same_clinic FOREIGN KEY (clinic_id, customer_id)
        REFERENCES customers (clinic_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_journal_author_same_clinic FOREIGN KEY (clinic_id, author_id)
        REFERENCES users (clinic_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_journal_signer_same_clinic FOREIGN KEY (clinic_id, signed_by_id)
        REFERENCES users (clinic_id, id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_journal_notes_customer ON journal_notes (clinic_id, customer_id, created_at DESC);

CREATE TABLE IF NOT EXISTS consents (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    signature_data TEXT NOT NULL,
    signed_by_user_id BIGINT,
    signed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_consent_customer_same_clinic FOREIGN KEY (clinic_id, customer_id)
        REFERENCES customers (clinic_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_consent_signer_same_clinic FOREIGN KEY (clinic_id, signed_by_user_id)
        REFERENCES users (clinic_id, id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_consents_customer ON consents (clinic_id, customer_id, signed_at DESC);

CREATE TABLE IF NOT EXISTS before_after_images (
    id BIGSERIAL PRIMARY KEY,
    clinic_id BIGINT NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL,
    journal_id BIGINT,
    image_type VARCHAR(10) NOT NULL CHECK (image_type IN ('before', 'after')),
    file_path VARCHAR(500) NOT NULL,
    area VARCHAR(100),
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_image_customer_same_clinic FOREIGN KEY (clinic_id, customer_id)
        REFERENCES customers (clinic_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_image_journal FOREIGN KEY (journal_id) REFERENCES journal_notes(id) ON DELETE SET NULL,
    CONSTRAINT fk_image_creator_same_clinic FOREIGN KEY (clinic_id, created_by_user_id)
        REFERENCES users (clinic_id, id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_images_customer ON before_after_images (clinic_id, customer_id, created_at DESC);

ALTER TABLE journal_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_templates FORCE ROW LEVEL SECURITY;
ALTER TABLE journal_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_notes FORCE ROW LEVEL SECURITY;
ALTER TABLE consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE consents FORCE ROW LEVEL SECURITY;
ALTER TABLE before_after_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE before_after_images FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS journal_templates_tenant ON journal_templates;
CREATE POLICY journal_templates_tenant ON journal_templates FOR ALL
USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'))
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));

DROP POLICY IF EXISTS journal_notes_select ON journal_notes;
CREATE POLICY journal_notes_select ON journal_notes FOR SELECT
USING (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND (customer_id IN (SELECT c.id FROM customers c WHERE c.user_id = lydia_context_bigint('lydia.current_user_id'))
         OR author_id = lydia_context_bigint('lydia.current_user_id')
         OR lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'))
);
DROP POLICY IF EXISTS journal_notes_insert ON journal_notes;
CREATE POLICY journal_notes_insert ON journal_notes FOR INSERT
WITH CHECK (
    clinic_id = lydia_context_bigint('lydia.current_clinic_id')
    AND author_id = lydia_context_bigint('lydia.current_user_id')
    AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')
);
DROP POLICY IF EXISTS journal_notes_update ON journal_notes;
CREATE POLICY journal_notes_update ON journal_notes FOR UPDATE
USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND is_signed = FALSE AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'))
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND is_signed = FALSE);
DROP POLICY IF EXISTS journal_notes_delete ON journal_notes;
CREATE POLICY journal_notes_delete ON journal_notes FOR DELETE
USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND is_signed = FALSE AND lydia_context_text('lydia.current_role') IN ('admin','superadmin'));

DROP POLICY IF EXISTS consents_access ON consents;
CREATE POLICY consents_access ON consents FOR ALL
USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND (customer_id IN (SELECT c.id FROM customers c WHERE c.user_id = lydia_context_bigint('lydia.current_user_id')) OR lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')))
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));

DROP POLICY IF EXISTS images_access ON before_after_images;
CREATE POLICY images_access ON before_after_images FOR ALL
USING (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND (customer_id IN (SELECT c.id FROM customers c WHERE c.user_id = lydia_context_bigint('lydia.current_user_id')) OR lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin')))
WITH CHECK (clinic_id = lydia_context_bigint('lydia.current_clinic_id') AND lydia_context_text('lydia.current_role') IN ('staff','admin','superadmin'));

CREATE OR REPLACE FUNCTION prevent_signed_journal_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_signed THEN
        RAISE EXCEPTION 'Signed journal is immutable: UPDATE and DELETE are forbidden.' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_prevent_signed_journal_update ON journal_notes;
CREATE TRIGGER trg_prevent_signed_journal_update BEFORE UPDATE ON journal_notes FOR EACH ROW EXECUTE FUNCTION prevent_signed_journal_modification();

CREATE OR REPLACE FUNCTION prevent_signed_journal_delete()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_signed THEN
        RAISE EXCEPTION 'Signed journal is immutable: DELETE is forbidden.' USING ERRCODE = '42501';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_prevent_signed_journal_delete ON journal_notes;
CREATE TRIGGER trg_prevent_signed_journal_delete BEFORE DELETE ON journal_notes FOR EACH ROW EXECUTE FUNCTION prevent_signed_journal_delete();

COMMIT;
