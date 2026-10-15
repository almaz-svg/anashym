# Независимая приемка полного MVP

## Финальный локальный повтор 2026-10-14

Ниже старый отчет сохранен как история найденных ошибок. Актуальные HTTP результаты против Waitress8000/PostgreSQL54329: `mvp_http.py`31 PASS; `mvp_edges.py`26 PASS; `mvp_scope_files.py`14 PASS; `mvp_cash_staff.py`14 PASS; `mvp_concurrency.py`12 PASS; `mvp_quarantine_archive.py`5 PASS; `mvp_security.py`44 PASS. Всего146 HTTP checks без ошибок. Security harness исправлен: customer cash корректно ожидает403.

Подтверждены structured JSON422 для шести фото и поврежденного PNG, EXIF removal/private cache/signature scope, quarantine fitness restoration ровно один раз, customer privacy weekly archives и точное совпадение frozen report arithmetic/IDs. CSV/source IDs и Decimal net равны JSON; ISO weekly groups согласованы. Конкурентные stock/quota/credit/handover limits проверены на PostgreSQL; собственные резервы и float очищены.

`mvp_courier_accountant.cjs`:13 PASS actual UI на свежих fixtures: courier photo upload/private preview, partial zero-row1600, cash3199 denied с сохраненным фото,3200 delivered; точный прирост клиентского долга1600. Accountant на360px скачал weekly CSV с traceability rows без overflow/pageerrors. `mvp_browser_actions.cjs`:3 PASS ранее в этой приемке (customer Kaspi form, cashier confirm, admin product form). Итого162 checks, из них3 ранее выполнены в этой приемке.

`mvp_cleanup.py`:18/18 явно отслеженных QA products деактивированы; бизнес-история не удалялась. Изолированные QA записи остаются; проверки сравнивают baseline deltas. Финальный повтор `mvp_browser.cjs` завершился exit0: все пять ролей ×360/768/1440 вошли и посетили все свои меню без alerts/pageerrors/горизонтального overflow. Результат: `qa/mvp-browser-results.json`. Предыдущий промежуточный timeout admin768 во время активного HMR в повторе не воспроизвелся; auth thresholds не менялись.

Основной агент отдельно проверяет backend suite, migration/backup restore,100k/500k benchmarks и постоянную WindowsTask. Эти доказательства не подменяются HTTP приемкой. Публичный deployment и внешние bank/SMS интеграции не заявлены: пользователь выбрал полностью локальную работу. Actual UI покрывает перечисленные формы, остальные сценарии проверены HTTP/backend tests.

## Дополнительные проверки окончательного интерфейса

Дополнительная приемка после последних UI изменений: `qa/mvp_final_ui.cjs`15 PASS. Admin создает заказ с точными client/address/quantity/payment_mode, собственный резерв затем отменяется штатным API. Свежий cashier открывает смену1000, выдает/возвращает float300, получает422 без причины расхождения и закрывает expected1000/count999/discrepancy-1; courier wallet0. Accountant cash read-only, refunds доступны, required category placeholder; pageerrors отсутствуют. `qa/mvp_accountant_refund_ui.cjs`2 PASS: бухгалтер через форму подтвердил собственный pending cash refund10; отдельное read-only ORM доказательство `qa/mvp-refund-cashbox-results.json` фиксирует ledger+10 и самостоятельную cashbox проводку-10.

`qa/mvp_settled_ui.cjs`1 PASS: открыта карточка настоящего fully returned order с server payment_status=settled; UI показывает «Расчёты закрыты». Последняя независимая UI приемка добавила24 PASS к предыдущим372checks (396 в сумме; отдельное ORM evidence не включено в count).

После финального restart: `qa/mvp_final_smoke.py`20 PASS (пять demo ролей сохранены, HTTP orders/payments/notifications); `qa/mvp_refusal_ui.cjs`4 PASS (реальная кнопка accept:false сохраняет instant исходной даты, удаляет предложение; до передачи скрыты нулевые settlement суммы, собственный резерв отменен). `qa/mvp_settled_ui.cjs`повторно1 PASS. QA harness сравнивает datetime instant вместо эквивалентных строк +05:00/UTC. Оба refusal fixtures отменены штатно,18/18 tracked products снова скрыты. Серверы/БД во время этих проверок не запускались и не останавливались. Общий count421 успешных assertions, включая повторные проверки, не уникальные требования ТЗ.

`qa/mvp_pagination_notification.cjs`6 PASS: staff orders20→40; customer history20→22; optional order selector20→22 реальных заказов. Открытый кабинет увидел событие отдельной сессии за925ms (ровно один sample, НЕ p95). Тестовый pending payment отклонен без проводки. Дополнительные9 QA orders отменены с освобождением резервов; все18 tracked products снова скрыты, float0. Промежуточные ошибки selectors/ожиданий были исправлены в QA harness, не в приложении. Новые UI итоги дополняют372checks предыдущей приемки.

## Серверные и эксплуатационные проверки координатора

Полный `manage.py test shop --noinput` после исправления авансов/возвратов: 58 PASS на PostgreSQL, 122.621 секунды. Затем отдельные 5 тестов догоняющей недельной генерации PASS. Django system check без замечаний, makemigrations --check --dry-run: No changes detected. Frontend: 8 tests PASS, production build PASS. После перезапуска реальные UI и API снова отвечают, readiness ready. Четыре PowerShell скрипта прошли синтаксическую проверку; автоматический worker повторяет задачи без дублирования.

Дополнительная резервная копия восстановлена в новую БД: 76 заказов, 60 проводок, 90 файлов, 0 расхождений балансов. Нагрузка на изолированных 100018 заказах/500018 строках: 3000 запросов, 0 ошибок, p95 375мс при равномерном старте50кабинетов. Синхронный всплеск даёт781мс и не укладывается в500мс; p95 создания заказов под нагрузкой не измерен. Полные условия и ссылки: local-operations.md. Эти ограничения остаются открытыми.

## История первичной приемки (устаревшие промежуточные результаты)

Статус: частичная независимая приемка, 2026-10-14 21:22 Asia/Almaty. Это не полный отчет PASS. Проверка выполняется против настоящего HTTP сервера localhost8000 и PostgreSQL127.0.0.1:54329; прямой вызов business services не заменяет приемку.

## Полученные доказательства

Команда `backend/.venv/Scripts/python.exe qa/mvp_http.py` прошла основной финансовый workflow через настоящие HTTP запросы: пять role logins, создание QA product/batch/order, replay одного Idempotency-Key и конфликт иного body, admin accepted/preparing/ready/out_for_delivery, отказ передачи без фото с неизменным балансом, настоящий multipart PNG201, charge15000, cash10000 → debt5000, handover10000 confirmed cashier сохраняет debt5000, return approve без receipt сохраняет5000, receive →3500, Kaspi pending сохраняет3500, confirm cashier → исходный baseline. Проверены envelopes orders/payments/notifications всех пяти ролей и customer audit403. JSON report200 имеет раздельные delivered/paid/return/refund/net totals. Финальный запуск остановился на CSV404: `?format=csv` перехвачен DRF format override до business handler; направлен root/backend, требуется fix и повторная приемка.

Результат `qa/mvp-http-results.json` содержит PASS основного workflow и финальный runner failure CSV. Изолированный ORM fixture только создает QA customer+delivery point; бизнес-операции исключительно HTTP. Несколько ранних запусков остановились до delivery из-за stale server и не изменили ledger. Один поздний запуск остановился на serializer `state` вместо фактического `status` после создания pending3500; его долг3500 остается демонстрационной записью, не удаляется. Тест сравнивает balance delta, поэтому не скрывает предшествующие остатки.

Команда `node qa/mvp_browser.cjs`: все пять ролей×360/768/1440 успешно вошли, прошли все видимые пункты меню, без alerts/pageerror и горизонтального overflow. Доказательства `qa/mvp-browser-results.json`, screenshots `qa/mvp-{role}-{width}.png`. Это проверка навигации/рендера, не доказательство выполнения каждого workflow.

Команда `node qa/mvp_browser_actions.cjs` PASS: customer заполнил настоящую форму Kaspi → server201 pending; cashier нашел именно этот reference и подтвердил через форму →200; admin создал товар через настоящую форму →201. Доказательства `qa/mvp-browser-actions-results.json`, `qa/mvp-action-kaspi-pending.png`, `qa/mvp-action-product.png`. Courier delivery и accountant report/period mutations через UI еще NOT RUN.

Найденные ранее ошибки и текущая граница: malformed PNG вызывал500 SyntaxError (root сообщил fix и5focusedPASS, независимый повтор invalidupload еще NOT RUN); stale server StockMovement NameError устранен restart/migration и actualdeliveryPASS; approve-before-receive ошибочно блокировался, теперь actualHTTPPASS; partial/zero lines/reserve freeing, preorder fullatomic conversion и cash endpoint получили запросы на исправление, требуют отдельных актуальных проверок.

GETcash ранее403 для staff; route/scoped totals остаются непроверенными после последних изменений. Security probe `qa/mvp_security.py` зафиксировал staff/customer denied product writes, customer audit403, courier clients403/ledger403. Матрица ожидаемых403 уточнена после первого запуска; текущий файл результатов не является полным PASS security.

`qa/mvp_http.py` — независимый stdlib HTTP runner: пять сессий, CSRF, ключи идемпотентности, настоящий multipart PNG. Основной денежный сценарий: доставка 10×1500 → долг15000; прием10000 → долг5000; физический возврат1500 → долг3500; Kaspi pending сохраняет3500; подтверждение кассиром →0. Сдача наличных не повторяет клиентский платеж. Невручение без фото проверяет rollback. Сохранение результата: `qa/mvp-http-results.json`.

Оставшиеся проверки — NOT RUN, кроме явно описанных выше:

- Доставка: full/partial, отказ, повторный dispatch, фото, cash shortage, physical goods quarantine.
- Оплаты: Kaspi pending/confirm/reject, duplicate reference/key, advance consent/refund bound.
- Касса: wallet available/pending, handover discrepancy, float, shift discrepancy reason.
- Реестр: FIFO/order allocation, period boundaries/snapshot, overdue, credit concurrency PostgreSQL.
- Отчеты: inclusive dates, weekly groups, CSV traceability/Decimal matching/formula escaping, role scope.
- Возвраты: quantity bounds, approval/receipt separation, quarantine, exchange current price and linked independent order.
- Пять ролей: actual actions and denied writes/foreign IDs, role session revocation.
- Предзаказ: quota→batch atomic fulfill, insufficient stock rollback, confirmed/rejected reschedule.
- Файлы/events: private bytes/header/access after completion, MIME/size/EXIF, notification rollback/scope/timing, audit secret redaction.
- Ops: root owns migration/deployment/backup restore/load evidence, to be linked when available.

Нельзя считать отсутствие HTTP ошибок доказательством бизнес-семантики. Каждая проверка должна измерять состояние до/после и отсутствие лишних денежных/складских записей. Browser QA будет исполнять операции через формы после обновления UI, с screenshots и pageerror сбором на360/768/1440.
