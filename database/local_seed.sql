-- Safe local-only test data. Passwords are intentionally simple development credentials.
-- This file is executed as the postgres administrator by `Lydia Local.command`.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO clinics (name)
SELECT 'Lydia Testklinik'
WHERE NOT EXISTS (SELECT 1 FROM clinics WHERE name = 'Lydia Testklinik');

WITH clinic AS (
    SELECT id FROM clinics WHERE name = 'Lydia Testklinik' ORDER BY id LIMIT 1
)
INSERT INTO users (clinic_id, email, password_hash, role, is_active)
SELECT clinic.id, 'admin@lydia.local', crypt('Admin123456!', gen_salt('bf')), 'admin', TRUE
FROM clinic
WHERE NOT EXISTS (SELECT 1 FROM users WHERE lower(email) = 'admin@lydia.local');

WITH clinic AS (
    SELECT id FROM clinics WHERE name = 'Lydia Testklinik' ORDER BY id LIMIT 1
)
INSERT INTO users (clinic_id, email, password_hash, role, is_active)
SELECT clinic.id, 'staff@lydia.local', crypt('Staff123456!', gen_salt('bf')), 'staff', TRUE
FROM clinic
WHERE NOT EXISTS (SELECT 1 FROM users WHERE lower(email) = 'staff@lydia.local');

WITH clinic AS (
    SELECT id FROM clinics WHERE name = 'Lydia Testklinik' ORDER BY id LIMIT 1
)
INSERT INTO users (clinic_id, email, password_hash, role, is_active)
SELECT clinic.id, 'customer@lydia.local', crypt('Customer123456!', gen_salt('bf')), 'customer', TRUE
FROM clinic
WHERE NOT EXISTS (SELECT 1 FROM users WHERE lower(email) = 'customer@lydia.local');

-- Keep the local test credentials deterministic when the persistent PostgreSQL
-- volume already contains these accounts. This is deliberately local-only.
UPDATE users
SET password_hash = crypt('Admin123456!', gen_salt('bf')), role = 'admin', is_active = TRUE
WHERE lower(email) = 'admin@lydia.local';

UPDATE users
SET password_hash = crypt('Staff123456!', gen_salt('bf')), role = 'staff', is_active = TRUE
WHERE lower(email) = 'staff@lydia.local';

UPDATE users
SET password_hash = crypt('Customer123456!', gen_salt('bf')), role = 'customer', is_active = TRUE
WHERE lower(email) = 'customer@lydia.local';

WITH u AS (
    SELECT id, clinic_id FROM users WHERE lower(email) = 'customer@lydia.local' LIMIT 1
)
INSERT INTO customers (clinic_id, user_id, first_name, last_name, email)
SELECT u.clinic_id, u.id, 'Test', 'Kund', 'customer@lydia.local'
FROM u
WHERE NOT EXISTS (SELECT 1 FROM customers WHERE user_id = u.id);

WITH u AS (
    SELECT id, clinic_id FROM users WHERE lower(email) = 'staff@lydia.local' LIMIT 1
)
INSERT INTO staff (clinic_id, user_id, display_name, is_active)
SELECT u.clinic_id, u.id, 'Test Personal', TRUE
FROM u
WHERE NOT EXISTS (SELECT 1 FROM staff WHERE user_id = u.id);

WITH clinic AS (
    SELECT id FROM clinics WHERE name = 'Lydia Testklinik' ORDER BY id LIMIT 1
)
INSERT INTO services (clinic_id, name, price, duration_minutes, is_active)
SELECT clinic.id, 'Konsultation', 500.00, 30, TRUE
FROM clinic
WHERE NOT EXISTS (
    SELECT 1 FROM services
    WHERE clinic_id = clinic.id AND name = 'Konsultation'
);
