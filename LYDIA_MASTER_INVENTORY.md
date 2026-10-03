# Lydia Estetisk Klinik — Master Source Inventory

Last collected: 2026-10-03

## Canonical sources
- Live WordPress: https://lydiaestetisk.se
- GitHub repository: https://github.com/Mirza22245/Iptv
- Connected WordPress tool: WPVibe
- Active theme: `lydia-estetisk-klinik` v2.0.0
- WPVibe draft: `lydia-estetisk-klinik-wpvibe-draft`

## WordPress environment
- WordPress: 7.1.2
- PHP: 8.3.33
- WPVibe: 1.20.0
- Active theme is WPVibe-authored and uses Tailwind.
- WP-CLI is available through WPVibe.
- Authenticated account is Administrator.
- WPVibe connection is verified for authenticated read access.
- Do not store secrets, passwords, application passwords, JWT secrets, database credentials, payment secrets, or private customer data in this repository.

## Active plugins
- hostinger-ai-assistant
- hostinger-easy-onboarding
- hostinger-reach
- hostinger
- litespeed-cache
- polylang
- google-site-kit
- woocommerce
- woocommerce-gateway-stripe
- woocommerce-payments
- insert-headers-and-footers
- wp-mail-smtp
- vibe-ai
- wp-sms

## Themes present
- hostinger-ai-theme
- lydia-estetisk-klinik-wpvibe-backup
- lydia-estetisk-klinik-wpvibe-draft
- lydia-estetisk-klinik
- twentytwentyfive
- twentytwentyfour
- twentytwentythree

## Active theme: 37 files
1. page-calendar.php
2. front-page.php
3. page.php
4. dist/styles.css
5. style.css
6. functions.php
7. template-parts/head.php
8. template-staff-portal.php
9. single.php
10. 404.php
11. index.php
12. page-lydia-personalpanel.php
13. archive.php
14. header-fix.js
15. page-kundportal.php
16. app-structure.css
17. assets/lydia.js
18. assets/js/alpine.min.js
19. language.css
20. header.php
21. page-lydia-calendar.php
22. single-lydia_service.php
23. template-journal-portal.php
24. page-personalportal.php
25. editor.css
26. booking.css
27. assets.js
28. header-fix.css
29. archive-lydia_service.php
30. staff-dashboard.css
31. footer.php
32. theme.css
33. calendar.css
34. page-adminpanel.php
35. app.css
36. page-lydia-dashboard.php
37. search.php

## Custom application architecture detected in theme
- `lydia_booking` custom post type for bookings.
- `lydia_feedback` custom post type for feedback.
- Booking shortcode: `[lydia_booking]`.
- Customer portal shortcode: `[lydia_customer_portal]`.
- Staff portal shortcode: `[lydia_staff_portal]`.
- Feedback shortcode: `[lydia_feedback]`.
- Booking availability AJAX action: `lydia_slots`.
- Booking management links use a token stored in booking post meta.
- ICS calendar output exists.
- Booking cancellation changes status to a custom `lydia_cancelled` post status.
- Hourly reminder cron exists.
- Email confirmation/reminder logic exists through `wp_mail`.
- Staff portal checks `current_user_can('edit_posts')`.
- Customer portal maps bookings by customer email.
- Demo customer portal exists behind `?demo=1`.
- Multilingual layer supports SV / EN / FA / AR and adds RTL for FA/AR.
- Schema markup for `MedicalClinic` exists on the front page.
- Meta description generation exists.

## Booking implementation currently in live theme
Defined service map in `functions.php`:
- Konsultation — 30 min — price 0
- Ansiktsbehandling — 60 min — price 0
- Hudbehandling — 60 min — price 0
- Estetisk behandling — 60 min — price 0

Current staff map:
- Kliniken

Current generated slots:
- Weekdays only.
- Current date or future dates only.
- 09:00 through the final slot that fits before 18:00.
- 30-minute increments.
- Existing bookings are removed from availability based on date/staff/duration overlap.

## Current published pages found
- `/feedback/` — Lämna feedback
- `/adminpanel/` — Adminpanel
- `/personalportal/` — Personalportal
- `/kundportal/` — Kundportal
- `/tjanster-boka/` — Tjänster & boka
- `/integrationer/` — Integrationscenter
- `/bokningsvillkor/` — Bokningsvillkor
- `/bokningsbekraftelse/` — Bokningsbekräftelse
- `/boka-behandling/` — Boka behandling online | Lydia Estetisk Klinik
- `/my-account/` — My account
- `/checkout/` — Checkout
- `/cart/` — Cart
- `/shop/` — Shop

## WooCommerce products found
- ID 103 — Lydia Hudvård
- ID 102 — Lydia Konsultation
- ID 97 — Lydia presentkort

## Media currently returned by REST inventory
- WooCommerce placeholder WebP: `woocommerce-placeholder.webp`

## `lydia_service` catalog
The site currently contains a large published service catalog. The catalog includes, among others:
- HIFU 12D hela ansiktet
- HIFU 12D hela ansiktet, hals och dubbelhaka
- HIFU 12D dubbelhaka
- HIFU 12D mage, kärlekshandtag
- HIFU 12D runt ögonen
- HIFU 12D hals och dubbelhaka
- EMsculpt 2 handtag
- EMsculpt 4 handtag
- Fettfrysning 2 handtag
- Fettfrysning 4 handtag
- Cavitation
- Babyface 5ml
- Läppfyllning
- Över ben
- Under ben
- Intim, bikinilinjen
- Intim, bikinilinjen, rumpa
- Hela armar
- Bröst, mage (dam)
- Rygg (dam)
- Armhålorna
- Hela ansiktet
- Hela ansiktet och hals
- Hela kroppen
- Rygg (herr)
- Bröst & mage (herr)
- Kemisk peeling & PRX hela ansiktet
- Kemisk peeling BioRePeelCI3
- Pigmentfläckar Meso White
- Ta bort tatuering upp till 4×4cm
- Ta bort tatuering upp till 8×8cm
- Microblading
- Lip Liner tatuering
- Eyeliner tatuering
- Ögonbrynstatuering
- Microneedling
- Vitalinjektor 2 – Vitaminterapi
- Hydrofacial med kollagen- och vitaminmask
- Håranalys med AI-teknologi
- Hårmesoterapi med Meso-Gun
- Konsultation
- Eksembehandling med laser 308nm
- Vitiligo behandling med laser 308nm
- Psoriasisbehandling med laser 308nm
- Piercing näsa
- Piercing tunga
- Piercing navel
- Piercing öra
- CO₂ Fraktionerad Laser – överläpp
- CO₂ Fraktionerad Laser – hals
- CO₂ Fraktionerad Laser – rygg
- CO₂ Fraktionerad Laser – dekolletage
- CO₂ Fraktionerad Laser – hela magen
- PRX-T Lady och mask
- Special Hydrofacial

There are also multiple duplicated service entries for some names, including `Bröst & mage (herr)` and `Kemisk peeling & PRX hela ansiktet`; these should be normalized later rather than silently deleted during collection.

## Live booking/feedback data status
- `lydia_booking`: currently 0 records returned by WP-CLI.
- `lydia_feedback`: currently 0 records returned by WP-CLI.
- This is a read-only inventory result at collection time, not a claim about historical records that may have existed elsewhere.

## Security / integrity observations for later engineering work
- Booking form uses WordPress nonces.
- Booking fields are sanitized before storage.
- Booking email is validated.
- Available time is revalidated server-side before insertion.
- Booking management URLs rely on a token stored in post meta.
- Cancellation endpoint is token-gated but should be reviewed later for replay/CSRF and authorization hardening.
- Customer portal is keyed by logged-in user's email and should later be reviewed for stronger object-level authorization.
- Staff access currently uses the broad `edit_posts` capability and should later be mapped to an explicit staff role/capability model.
- Current booking storage is WordPress posts/meta, not the previously discussed FastAPI/PostgreSQL schema.
- Therefore the earlier FastAPI/Docker Gate v2.2 architecture is NOT yet present in this WordPress source inventory.

## Collection rule
This repository is the engineering source-of-truth for the collected Lydia material. Collection must not modify the live site. Before production refactors, preserve the current WordPress theme as a reference snapshot and keep credentials/secrets out of Git.

## Next build order
1. Finish source-file transfer from the WPVibe draft into `source/wordpress-theme/`.
2. Capture structured page/product/service inventories under `source/wordpress-content/`.
3. Capture configuration/integration inventory without secrets.
4. Compare current WordPress architecture with the intended FastAPI/PostgreSQL/RBAC architecture.
5. Build only the missing pieces after the comparison is complete.
