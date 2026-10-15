# Полный MVP: ownership, приемка и границы пилота

ТЗ: source-tz.txt v0.2. Contract: mvp-contract.md. План охватывает все оставшиеся модули; список ниже не является отчетом о завершении. Только демонстрационные данные, ручная сверка Kaspi.

## Ownership без конфликтов файлов

- mvp_backend: backend/shop/models.py, migrations, views/services/routes/serializers, seed и backend business tests. Единственный владелец schema. Все финансовые и складские actions транзакционные; idempotency для всех изменяющих бизнес-запросов.
- mvp_frontend: frontend/src, typed API, все пять role workspaces, сохранение текущего зеленого интерфейса; role-specific forms, loading/empty/error/success, серверные validation errors, upload draft/retry, 360/768/1440.
- root coordinator: backend/shop/private_files.py после согласования Attachment schema, private-file tests, ops scripts, compose/settings/readiness/backup/restore/load checks, интеграция и итоговая сверка ТЗ.
- mvp_architect: docs/mvp-contract.md и этот план; contract coordination. Не редактирует production code.
- tester (после освобождения слота архитектора): независимая приемка маршрутов и UI, role/security denial, PostgreSQL concurrency, qa.md с доказательствами и честным статусом.

## Обязательные приемочные сценарии

1. Delivery: accepted→ready→dispatch→full/partial delivery. Photo required; cash shortfall blocks atomically; deferred charge only accepted portions. Failed creates zero debt; retry does not dispatch stock twice; physical return goes quarantine. Retry same key creates one attempt/charge/cash movement.
2. Payments: Kaspi pending changes neither debt nor acceptance; confirm creates one posting, unique external reference across clients, amount mismatch partial/advance. Cash received-change with evidence; excess requires consent. Refund <=advance, repeated confirm safe.
3. Cash: courier 10000 receipt→7000 pending handover→second request exceeding available rejected; confirm actual 6500 reason records discrepancy and moves only 6500. Client debt unchanged by handover. Float issue/return not client payment. Shift open/close expected vs actual; mismatch requires reason.
4. Periods/allocation: 7/14/30 anchor boundary local midnight; period uses delivered_at. Charge 30000, payment10000, return5000 => debt15000. FIFO by due/event/id; order-specific allocation; excess advance; closed snapshot immutable after late payment; overdue blocks only new deferred orders. Concurrent credit orders cannot exceed limit.
5. Reports: arbitrary inclusive dates, weekly ISO groups, CSV IDs and exact Decimal totals equal ledger; pending excluded from paid; formula injection escaped; every role scope excludes foreign organizations/contact data.
6. Returns/exchange: delivered quantity bounds including concurrent requests; approval separate from physical receipt; no credit until received or explicit no-collection reason; no automatic stock availability. Replacement order linked exchange_id uses current price/reserve; difference uses ordinary settlements.
7. Five roles: customer purchases and own history; courier only active assignment and own wallet; cashier reviews and cash shifts; accountant ledger/periods/reports; admin stock/clients/staff/returns/audit. Direct API forbidden writes 403, foreign object404. Role change invalidates session. UI exposes actual actions, not placeholders.
8. Preorder: quota reserve→actual batch atomic conversion; insufficient actual stock leaves all quota/reserves unchanged; ready blocked until converted; reschedule customer-confirmed with quota move, rejection retains date; prepaid cancellation yields advance/refund obligation.
9. Files/events: byte signatures,10MB/40MP/5 limits, EXIF removed, private unauthorized/foreign/completed courier denial, cashier cash-only evidence. Notifications after commit, rollback produces none; UI <=2s target measured under normal RTT; append-only audit includes reason/request_id but no secrets.
10. Deployment: reproducible frontend build, backend tests/migrations/system check --deploy, PostgreSQL concurrency (not SQLite substitute), health/readiness includes DB, worker expiration/period closure idempotent, backup+restore drill, restricted secrets/cookies/HTTPS, measured load50 visible cabins with100k orders/500k lines and polling. Container start validated where runtime available.

## Test execution/reporting

Backend owner adds focused tests for invariants above. Frontend owner runs build and API integration checks. Independent tester replays representative happy/negative paths and all role scopes against actual HTTP server. Existing qa.md prior-slice PASS does not prove new modules. Record command, environment, timestamp, observed result; mark NOT RUN/BLOCKED with reason instead of inferred success. PostgreSQL concurrency requires real PostgreSQL and must be explicitly distinguished from SQLite smoke tests.

## Honest pilot blockers (require evidence to clear)

- Contract completion is not implementation completion: all routes, actions and UI must be reconciled against runtime and test evidence before saying all10 items done.
- Real Kaspi contractual API/automatic debit is intentionally out of MVP; manual reconciliation requires authorized seller account and operational procedure. No fabricated payment success.
- Admin second factor, invitations/password reset and session revocation must be working for pilot; demo passwords are not production access management.
- Deployment provider/domain/HTTPS/secrets/private persistent storage, migrations and scheduled worker must be configured in target environment; local build alone is not deployed readiness.
- PostgreSQL race tests, backup restoration and realistic load targets remain unverified until executed. Performance p95/read<500ms/create<1s/event<=2s are targets, not claims.
- Product owner/accountant must confirm period anchors/limits, photo retention/data residency, cash discrepancies/refunds, and technical photo failure exception before real customer data. Existing approved TЗ authorizes implementation; these are operational launch settings, not a request to stop development.
- Production security checks include no public media, proper role scope after assignment completion, immutable ledger/audit and safe CSV; any failed check blocks real-data pilot.

## Final reconciliation format

For each of10 items: implemented routes/UI, relevant test evidence, limitations. Complete only if mandatory business semantics are implemented. Separate “implemented and tested locally”, “target-environment verification pending”, and “not implemented”. Keep root README/runbook and qa.md synchronized with actual behavior.

## Локальная сверка 14.10.2026 после доработок

| Пункт | Реализация и проверка | Граница |
| --- | --- | --- |
| Доставка | Подготовка, назначение, выезд, фото, полная/частичная передача, неудача, сдача товара в карантин; HTTP и реальные формы курьера | Только тестовые заказы |
| Отдельные оплаты | Kaspi pending/confirm/reject, наличные, частичные суммы, авансы и возвраты; финансовая регрессия | Реального Kaspi API нет, предусмотрена ручная сверка |
| Касса | Кошелёк курьера, сдача, подотчёт, открытие/закрытие смены, расхождение с причиной; HTTP и формы | Учёт оперативный, интеграции ККМ нет |
| Задолженность | Начисление при передаче, 7/14/30 дней, сроки/просрочка, распределение, неизменные закрытые снимки; PostgreSQL tests | Реальные лимиты/правила пилота ещё не настроены |
| Отчёты | Произвольные даты, отдельные оборот/оплаты/долг, CSV, недельный архив и догоняющая генерация | Автоматика выполняется при включённом компьютере |
| Возвраты и обмены | Заявка/решение/приём, карантин/пригодность/списание, корректировка, отдельный refund, связанный новый заказ | Часть вариантов проверена HTTP, не каждый вариант через браузер |
| Пять кабинетов | Клиент, администратор, курьер, кассир, бухгалтер; права проверены API, основные действия — UI; добавлена история страницами | Полная production-аутентификация со вторым фактором отложена |
| Предзаказы | Квота в фактические партии, атомарность обеспечения, согласование/отказ переноса | Поздний UI-повтор отказа записан в QA отдельно |
| Уведомления/фото/аудит | Опрос, приватный доступ и подписи, очистка EXIF, ограничения файлов, журнал; security tests | 925 мс уведомления — одиночный замер, не p95 |
| Эксплуатация | Постоянная Windows task, health/readiness, ежедневная копия, реальное восстановление, 100k/500k benchmark | p95 равномерного чтения375мс, синхронный всплеск781мс; хостинг/HTTPS и p95 массового создания не подтверждены |

Последний полный backend run: 58 тестов PASS на PostgreSQL, затем 5 focused tests недельной генерации PASS. Последняя frontend сборка PASS; 8 tests PASS. Подробная граница браузерной/HTTP приёмки — mvp-qa.md; результаты нагрузки и восстановления — local-operations.md. Это не объявление готовности к реальным банковским операциям или полного выполнения production-пункта10. Полный OpenAPI после первого среза ещё не синхронизирован.
