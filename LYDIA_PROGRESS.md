# Lydia – Progress & Continuation Log

_Last updated: 2026-10-04_

## Current status

Lydia has a substantial database/security foundation in place. Work must continue from the existing architecture rather than creating parallel models or APIs.

### Verified from repository

- PostgreSQL CI workflow exists in `.github/workflows/test.yml`.
- CI uses PostgreSQL 17.
- CI creates `lydia_app` as `NOSUPERUSER NOBYPASSRLS`.
- CI validates that `lydia_app` remains non-superuser and cannot bypass RLS.
- CI validates the migration files exist and executes them in this order:
  1. `database/schema_v2.sql`
  2. `database/phase2_clinical.sql`
  3. `database/phase3_business.sql`
- CI validates the expected core, clinical and Phase 3 tables exist.
- CI prints/verifies RLS metadata (`relrowsecurity`, `relforcerowsecurity`).
- CI runs `pytest -q` against PostgreSQL using `lydia_app`.
- Phase 3 database schema exists in `database/phase3_business.sql` with products, inventory movements, sales, sale items, payments, integrations and report snapshots, including RLS policies.

## Important: not yet proven

Do **not** call Lydia production-ready or CI-green until GitHub Actions reports a successful run for the latest commit. The available GitHub connection currently shows no workflow run associated with the latest CI commit.

## Remaining implementation work

### P0 – CI and security gate

- Confirm GitHub Actions run starts for the latest workflow commit.
- If CI fails, inspect the actual job logs and fix the repository directly.
- Confirm PostgreSQL integration tests exercise the real RLS context (`lydia.current_clinic_id`, `lydia.current_user_id`, `lydia.current_role`) rather than mocked tenant isolation.
- Confirm all relevant RLS policies are `FORCE ROW LEVEL SECURITY` where required.
- Confirm signed clinical records and audit records are immutable at the database layer, not only at the API layer.

### P0 – Clinical Phase 2 completion

- Verify journal CRUD/signing endpoints against the real asyncpg/RLS context.
- Verify customer/clinic tenant isolation through API and database tests.
- Complete consent creation, versioning, retrieval and signature handling.
- Complete before/after image metadata and secure storage integration.
- Complete journal templates and validation of template structures.
- Add real integration tests for all of the above.

### P0 – POS / checkout

The Phase 3 database foundation exists, but the repository must still be verified for a complete transactional checkout implementation.

Required flow:

1. Validate authenticated clinic/user/role context.
2. Validate every product/service belongs to the current clinic.
3. Calculate totals and VAT server-side using exact decimal/numeric arithmetic.
4. Create `sales` and `sale_items` atomically.
5. Create `payments` atomically.
6. Decrease product stock atomically and create `inventory_movements`.
7. Reject insufficient stock without partial writes.
8. Make checkout idempotent so retries cannot create duplicate sales/payments.
9. Write an audit event.
10. Return a persistent receipt identifier from the database, not a timestamp-derived fake identifier.

### P1 – Receipts

- Persistent receipt numbering. **Implemented; awaiting green CI verification.**
- Receipt rendering/printing/export.
- VAT breakdown.
- Customer receipt lookup.
- Refund/void handling with audit trail.

### P1 – Cash register / Z-report

- Open/close register session.
- Opening cash balance.
- Cash movements.
- Sales totals by payment method.
- VAT totals.
- Closing balance and variance.
- Immutable Z-report/daily closing record.
- Prevent double-closing the same register/day.

### P1 – Gift cards / treatment cards

- Gift card issuance, balance, redemption, refund rules and audit trail.
- Treatment/clip-card issuance and redemption.
- Atomic balance updates and concurrency protection.

### P1 – Inventory

- Product CRUD.
- Stock adjustment/purchase/return/waste flows.
- Low-stock reporting.
- Stock history.
- Concurrency-safe stock updates.

### P1 – Reports

- Revenue and VAT reports.
- Sales by product/service/staff.
- Payment-method breakdown.
- Inventory reports.
- Booking/no-show/retention reports where source data exists.
- CSV/XLSX export.
- RLS-safe report queries.

### P2 – Secure file storage

- UUID-based object/file keys.
- MIME/type and size validation.
- No user-controlled filesystem paths.
- Clinic-scoped access checks.
- Secure download/preview endpoints.
- Storage abstraction suitable for local Docker and S3-compatible production storage.

### P2 – External integrations

Do not invent external API contracts.

Implement only after real provider documentation/credentials/contracts are available:

- Bokadirekt.
- Meridiq.
- BankID.
- Stripe/Swish or other payment providers.

The existing integration tables can store configuration/events, but external API behavior must be implemented from actual contracts.

### P2 – Operations / production hardening

- Automated PostgreSQL backups and restore test.
- Session/revocation management.
- Rate limiting.
- Security headers and CORS review.
- Secrets management.
- Structured application logging.
- Monitoring/health checks.
- Migration rollback/recovery strategy.
- Final RLS/security audit.

## Recommended execution order

1. **Get CI green and inspect real logs.**
2. **Finish/verify Phase 2 clinical integration tests.**
3. **Implement transactional POS checkout.**
4. **Implement persistent receipts.**
5. **Implement register open/close and Z-report.**
6. **Implement gift cards and treatment/clip cards.**
7. **Finish inventory workflows.**
8. **Build reports and exports.**
9. **Finish secure file storage.**
10. **Implement external integrations only from real contracts.**
11. **Run final production/security/backup review.**

## Working rule

Never mark a feature "done" because code exists. Mark it done only when:

- repository implementation exists,
- tenant/RLS behavior is tested,
- authorization is tested,
- failure/rollback paths are tested,
- concurrency/idempotency is tested where relevant,
- CI passes against PostgreSQL,
- and the actual GitHub Actions result is green.

## Last known CI state

Latest CI-related commit checked: `35f0bcb23e42f7d94e094fa4d3afb0f9f8063e41`.

At the time of this log update, the GitHub connection returned **no workflow run associated with that commit**, so CI status remains **PENDING / NOT VERIFIED**.
