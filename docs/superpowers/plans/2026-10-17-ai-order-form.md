# AI order draft implementation

User approved TZ 1.2 and overrides: preserve current actor/client semantics, no raw-text persistence, mandatory 90% acceptance. Provider unavailable: no paid requests, no mock AI in the live app.

1. Add strict server contract and nonpersistent parse service with an injectable adapter for tests, disabled in runtime until provider/budget/privacy approval.
2. Add admin-only message/review form, manual fallback, explicit confirmation, server prices, same `/orders` operation. Clear on close/success; discard late responses. Raw message goes only to parse endpoint, never mutation/idempotency caches or storage.
3. Add Russian/Kazakh/English copy and responsive existing-token styling. Test disabled state, correction, no reservations during parse, invalid outputs, failure retention and clearing.
4. Run focused/backend regression and frontend suite/build, review and inspect local UI at mobile/desktop.

Design lock: existing `admin-order.tsx` supplies labels/selects/order fields; `customer-profile.tsx` supplies paired responsive panels; `style.css` supplies Manrope, green primary, neutral surfaces and existing borders. Refero live style/screen searches attempted but unavailable (NO_SUBSCRIPTION); fallback craft-details and copywriting references inspected. Preserve current tokens, two labelled panels (source / review), explicit unavailable notice, one final order action. No new visual language or decorative AI elements.

Known baseline: 3 existing finance/access test failures; incomplete unrelated cloud tests remain outside scope. No claim of measured AI accuracy until provider is connected and real outputs are evaluated.
