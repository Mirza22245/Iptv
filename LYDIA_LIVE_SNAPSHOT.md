# Lydia Live Snapshot — 2026-10-03

## Counts
- Published WordPress pages: 13
- Published `lydia_service` posts: 78
- Published WooCommerce products: 3
- Current `lydia_booking` records: 0
- Current `lydia_feedback` records: 0
- Active theme files in WPVibe draft: 37

## WordPress routing/configuration
- Site title: Lydia Estetisk Klinik
- Home URL: https://lydiaestetisk.se
- Permalink structure: `/%postname%/`
- WordPress menus: none returned by WP-CLI; the current header navigation is rendered by the theme.
- WooCommerce shop page ID: 5
- WooCommerce cart page ID: 6
- WooCommerce checkout page ID: 7
- WooCommerce My Account page ID: 8

## Homepage currently renders
- Top bar: Göteborg / Onlinebokning / Personlig service
- Header brand: Lydia / ESTETISK KLINIK
- Navigation: Hem, Boka behandling, Kundportal, Kontakt
- Hero: “Din hud. Din skönhet. Din tid.”
- Hero positioning: modern technology, personal care, calm/exclusive feel
- Services section with service cards, prices and booking links
- About section mentioning Södra Allégatan 1B in Göteborg
- Account section
- Journal/clinical module teaser restricted to authorized staff
- Online booking section
- Lydia Rewards / referral section
- Final CTA
- Footer

## Live homepage data quality finding
The rendered homepage currently shows repeated service cards for some services. In particular, `Bröst & mage (herr)` and `Kemisk peeling & PRX hela ansiktet` appear repeatedly because multiple published `lydia_service` posts exist for the same logical service. This should be normalized as a controlled data-cleanup task later; do not delete anything during collection.

## Service catalog examples with rendered price/duration
- Armhålorna — 20 min — 1190 kr
- Babyface 5ml — 20 min — 1490 kr
- Bröst & mage (herr) — 20 min — 1290 kr
- Bröst, mage (dam) — 20 min — 1049 kr
- Cavitation — 15 min — 1099 kr
- CO₂ Fraktionerad Laser – dekolletage — 60 min — 3990 kr
- CO₂ Fraktionerad Laser – hals — 30 min — 3490 kr
- CO₂ Fraktionerad Laser – hela magen — 60 min — 5990 kr
- CO₂ Fraktionerad Laser – överläpp — 20 min — 990 kr
- CO₂ Fraktionerad Laser – rygg — 30 min — 2990 kr
- Eksembehandling med laser 308nm — 25 min — 1990 kr
- EMsculpt 2 handtag — 30 min — 1990 kr
- EMsculpt 4 handtag — 30 min — 2990 kr
- Eyeliner tatuering — 90 min — 2290 kr
- Fettfrysning 2 handtag — 20 min — 1990 kr
- Fettfrysning 4 handtag — 40 min — 3890 kr
- Håranalys med AI-teknologi — 30 min — 699 kr
- Hårmesoterapi med Meso-Gun — 30 min — 0 kr
- Hela ansiktet — 15 min — 999 kr
- Hela ansiktet och hals — 18 min — 1490 kr
- Hela armar — 15 min — 1099 kr
- Hela kroppen — 90 min — 3990 kr
- HIFU 12D dubbelhaka — 15 min — 1390 kr
- HIFU 12D hals och dubbelhaka — 15 min — 2390 kr
- HIFU 12D hela ansiktet — 30 min — 3480 kr
- HIFU 12D hela ansiktet, hals och dubbelhaka — 40 min — 3980 kr
- HIFU 12D mage, kärlekshandtag — 30 min — 3490 kr
- HIFU 12D runt ögonen — 15 min — 1790 kr
- Hydrofacial med kollagen- och vitaminmask — 50 min — 2290 kr
- Intim, bikinilinjen — 20 min — 1290 kr
- Intim, bikinilinjen, rumpa — 20 min — 1790 kr
- Kemisk peeling & PRX hela ansiktet — 45 min — 1490 kr
- Kemisk peeling BioRePeelCI3 — 40 min — 1990 kr
- Konsultation — 15 min — 0 kr
- Läppfyllning — 90 min — 2490 kr
- Lip Liner tatuering — 90 min — 2290 kr
- Microblading — 90 min — 2390 kr
- Microneedling — 60 min — 1690 kr
- Ögonbrynstatuering — 90 min — 2490 kr
- Över ben — 15 min — 990 kr
- Piercing näsa — 15 min — 990 kr
- Piercing navel — 15 min — 1290 kr
- Piercing öra — 15 min — 990 kr
- Piercing tunga — 15 min — 1290 kr
- Pigmentfläckar Meso White — 45 min — 1990 kr
- PRX-T Lady och mask — 45 min — 1490 kr
- Psoriasisbehandling med laser 308nm — 25 min — 990 kr
- RF ansikte, hals, dubbelhaka — 35 min — 2590 kr
- RF hals och dubbelhaka — 25 min — 990 kr
- RF hela ansiktet — 35 min — 1990 kr
- Rygg (dam) — 15 min — 990 kr
- Rygg (herr) — 20 min — 1190 kr
- Special Hydrofacial — 60 min — 2590 kr
- Ta bort tatuering upp till 4×4cm — 15 min — 990 kr
- Ta bort tatuering upp till 8×8cm — 15 min — 1490 kr
- Under ben — 15 min — 990 kr
- Vitalinjektor 2 – Vitaminterapi — 60 min — 3990 kr
- Vitiligo behandling med laser 308nm — 25 min — 1990 kr

## Important architecture mismatch
The live site is still a WordPress/PHP/WooCommerce application. The previously discussed FastAPI/PostgreSQL/RBAC/Docker architecture has not been verified as present on this site. Treat that architecture as a future target, not as deployed functionality.

## Safe continuation rule
Continue collection and analysis first. Do not publish a theme, alter live content, delete duplicate services, change roles, or migrate data until the collected source is reviewed and a concrete migration/build plan is approved.
