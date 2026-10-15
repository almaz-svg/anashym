# Полный MVP: REST contract для реализации

Источник: `source-tz.txt` v0.2. Это согласованный интерфейс реализации, а не заявление о прохождении приемки. Данные только демонстрационные. Реального Kaspi API нет: сотрудник вручную сверяет поступление в кабинете продавца.

## Общие правила

База `/api/v1`. JSON snake_case, UUID строками (существующие batch/quota могут иметь integer ID), денежные значения строками Decimal с двумя знаками; ответы используют суффикс `_amount`. RFC3339 с offset; бизнес-даты Asia/Almaty. GET коллекции `{items:[],next_cursor:null}`, `limit=1..100`, cursor opaque. GET объекта возвращает объект без envelope. POST create 201, action 200; logout 204.

Session cookie HttpOnly, CSRF cookie + X-CSRFToken для всех изменений. POST бизнес-операций требует `Idempotency-Key` UUID: одинаковый body возвращает сохраненный ответ; иной body с тем же ключом 409 IDEMPOTENCY_CONFLICT. Транзакция включает событие, деньги, запасы, аудит и уведомление. Версия заказа обязательна для конфликтующих действий; stale version → 409 VERSION_CONFLICT. Ошибка `{code,message,field_errors,details,request_id}`. Чужой объект 404; запрещенное действие над видимым объектом 403. Никаких DELETE финансовой истории.

Роли: admin, customer, courier, cashier, accountant. Customer видит организацию; courier активные назначения и собственную обезличенную сменную сводку; cashier денежные операции; accountant все финансы; admin все рабочие данные. Эти ограничения серверные.

## Сессия и справочники

- GET `/auth/csrf`; POST `/auth/login` `{phone,password}`; GET `/auth/me` `{user_id,role,client_id,approval_status,name,phone,client_name}`; POST `/auth/logout`.
- POST `/auth/register`: существующие поля анкеты + optional `requested_period_days:7|14|30`. Pending клиент не получает доступ к заказам до одобрения. Телефон не считается проверенным без OTP.
- GET `/catalog?delivery_date=YYYY-MM-DD`: существующий product serializer. GET `/delivery-points`: подтвержденные точки customer; admin может фильтровать client_id.
- GET `/clients`, GET `/staff` для сотрудников по роли (полные настройки admin). POST `/clients/{id}/approve` `{approval_status,deferred_approved,credit_limit_amount,period_days,period_start,reason}` admin. Изменение периода действует со следующей границы. POST `/staff` `{phone,name,role}` admin; установка пароля через приглашение. Изменение роли отзывает сессии. Конкретная реализация CRUD должна пройти отдельную проверку, эти endpoints не заменяются прямым редактированием БД.
- POST `/products`, `/batches`, `/quotas` admin: product `{name,description,price_amount,preparation_minutes}`; batch `{product_id,manufactured_at,expires_at,quantity}`; quota `{product_id,date,cutoff,quantity}`. Корректировка партии отдельным движением с reason. GET `/batches`, `/quotas` admin.

## Заказы и доставка

GET `/orders`, GET `/orders/{id}`. Order сохраняет существующие поля и добавляет `courier_id`, `delivered_at`, `partial`, `delivered_amount`, `paid_amount`, `outstanding_amount`, `photo_ids`, `events`, `reschedule_proposal`, `exchange_id`; items добавляют `delivered_quantity`. Контакты только для разрешенных ролей/активного назначения.

- POST `/orders`: `{kind:regular|preorder,delivery_point_id,requested_delivery_at,payment_mode:deferred|kaspi|cash,items:[{product_id,quantity,expected_unit_price}],client_id?,exchange_id?}`. Customer self; admin от клиента. Атомарный FEFO резерв или квота. Deferred проверяет approval, overdue, balance+reserve. Kaspi 30 минут; cash/deferred 60 минут до принятия.
- POST `/orders/{id}/transition`: `{status,courier_id?,reason?,version}`. Admin accepted→preparing→ready→out_for_delivery, cancel до выезда; courier только назначенный выезд. Kaspi accepted только при полной подтвержденной оплате. Ready preorder требует batch резерв. Выезд делает dispatch один раз; повторная попытка не списывает склад снова.
- POST `/orders/{id}/delivery`: `{items:[{product_id,quantity}],photo_ids:[UUID],payment_received_amount?,cash_received_amount?,cash_change_amount?,advance_consent?,reason?,version}`. Назначенный courier или admin с reason. `photo_id` принимается как совместимый одиночный ID. Каждая строка обязательна, целое 0..ordered, минимум одна принятая порция. Начисление по принятым строкам и snapshot price; reserve освобождается полностью. Partial остается delivered; непереданные товары у курьера до физической сдачи в quarantine. Cash net=received-change; cash заказ нельзя вручить с недостатком; избыток только с согласием клиента. Фото обязательно; upload failure не позволяет successful delivery.
- POST `/orders/{id}/delivery-failed`: `{reason,version}` courier/admin. Нет начисления, товар остается у курьера. Следующий dispatch — новая attempt в том же заказе.
- POST `/orders/{id}/payment-mode`: `{payment_mode:deferred,reason,version}` admin; проверяет одобрение и лимит. Courier режим не меняет.
- POST `/orders/{id}/goods-return`: `{items:[{product_id,quantity}],reason}` admin принимает недоставленное в карантин; не увеличивает продаваемый остаток.

## Предзаказ

- POST `/orders/{id}/fulfill`: `{batches:[{product_id,batch_id,quantity}],version?}` admin. Actual batches должны покрывать все строки. В одной транзакции снимает quota reserve, ставит batch reserve; недостаток отклоняет весь запрос. Производство оформляется созданием фактической партии до fulfill.
- POST `/orders/{id}/reschedule`: `{requested_delivery_at,reason,version?}` admin создает предложение, не меняет дату без клиента.
- POST `/orders/{id}/reschedule-confirm`: `{accept:true|false,version?}` customer. При accept атомарно переносит quota reserve на новую дату. Reject сохраняет прежнюю дату; admin может cancel. Предоплаченная отмена оставляет advance/refund obligation.

## Платежи, реестр и периоды

- GET `/payments`; POST `/payments` `{client_id?,order_id?,method:kaspi|cash,amount:string,reference?,photo_ids?,cash_received_amount?,cash_change_amount?,advance_consent?}`. Customer/courier создают Kaspi заявку pending_review; cashier/accountant/admin сверяют. Cash courier доступен для назначенной доставки или явно назначенного admin сбора старого долга; фото обязательно. Cash создается confirmed при факте приема и cash movement в courier wallet. Нет автоматического подтверждения кнопкой клиента.
- POST `/payments/{id}/confirm` `{reference?,reason?}` cashier/accountant, admin с reason. Уникальный reference Kaspi; повтор не уменьшает баланс. POST `/payments/{id}/reject` `{reason}`.
- Payment response `{id,client_id,order_id,method,amount,state,reference,created_at,confirmed_at,allocations:[{entry_id,amount}],unallocated_amount,cash_holder_id}`; где `amount` — строка, serializer может дополнительно отдавать `amount_amount` не требуется.
- GET `/ledger?client_id=&from=&to=`: неизменяемые entries `{id,client_id,order_id,kind,amount,event_at,business_date,period_id,author_id,reverses_entry_id}`. Плюс charge/refund, минус payment/return_credit. Balance = sum ledger; cached client balance не единственный источник истины.
- GET `/balance?client_id=`: существующий balance response. GET `/periods?client_id=`: `{id,client_id,start,end_exclusive,due_at,closed_at,snapshot,current_outstanding_amount}`. Snapshot immutable, late payments не переписывают его.
- POST `/periods/close` `{as_of?}` accountant/admin; worker выполняет то же идемпотентно по client/start. FIFO allocation по due_at,event_at,id; order_id задает явное распределение. Остаток платежа advance; возврат кредита уменьшает открытые allocations корректно.
- POST `/refunds` `{client_id,amount,method,reason,original_payment_id?}` cashier/accountant/admin; POST `/refunds/{id}/confirm` `{reference?,reason?,photo_ids?}`. Подтверждение не больше доступного advance, отдельная положительная запись; повтор безопасен.

## Наличные, касса, смены

- GET `/cash` scoped wallet totals `cash_amount,pending_handover_amount,available_amount`. GET `/handovers`; POST `/handovers` `{amount}` courier резервирует доступные наличные. POST `/handovers/{id}/confirm` `{amount,reason?}` cashier/admin. Разница обязательно с reason, переносится только фактическая сумма; клиентский payment не создается повторно. POST `/handovers/{id}/reject` `{reason}` освобождает резерв.
- GET `/shifts`; POST `/shifts` `{action:open|close,opening_amount?,actual_amount?,reason?}` cashier/admin. Close сохраняет expected/actual/discrepancy, ненулевая разница требует reason; одна открытая смена кассира.
- GET `/cash-movements`; POST `/cash-movements` `{courier_id,amount,direction:issue|return,reason}` cashier/admin, внутренний подотчет не payment клиента.

## Возврат и обмен

- GET `/returns`; POST `/returns` `{order_id,kind:return|exchange,items:[{product_id,quantity}],reason,photo_ids}` customer/назначенный courier/admin. Ограничение delivered минус уже одобренное и зарезервированное pending количество, серверная snapshot price.
- POST `/returns/{id}/receive` `{reason,photo_ids}` admin/courier по назначению: physical_state=received, quarantine movement. Финансовое решение отдельно.
- POST `/returns/{id}/decide` `{decision:approve|reject,reason,without_collection?,disposition:quarantine|write_off}` admin. Approve без физического приема оставляет awaiting_receipt; кредит проводится только received либо explicit without_collection. Quarantine не продается. Пригодность/возврат в доступную партию требует отдельного stock action.
- Exchange response содержит `exchange_id`; новый POST orders с этим exchange_id проходит обычный резерв и snapshot новой цены. Старые строки не редактируются. Return и replacement order имеют независимые статусы; разница оплачивается обычными payment/deferred/refund.

## Файлы, аудит, уведомления, отчеты

- POST `/files` multipart `file,order_id,purpose` + CSRF/idempotency; 201 `{id,order_id,purpose,mime,size,content_hash,created_at}`. 1–5 JPEG/PNG/WebP/event, каждый <=10MB, <=40MP; декодирование и перекодирование, удаление EXIF. Нет публичного media URL. GET `/files/{id}` проверяет актуальный доступ и возвращает private bytes `Cache-Control:private,no-store` (либо signed URL <=300sec с повторной авторизацией). Cashier только cash evidence, courier только активное задание. Metadata Attachment согласуется с backend schema, root делает helper.
- GET `/notifications?after=` scoped `{items:[{id,kind,message,object_id,created_at,read_at}],next_cursor}`; POST `/notifications/{id}/read` `{}`. Опрос видимого кабинета 1s, backoff при ошибке, дата последнего успеха. События только после commit.
- GET `/audit` admin/accountant scope: `{id,actor_id,action,object_type,object_id,before,after,reason,request_id,created_at}`. Без секретов и полных контактов.
- GET `/reports?from=YYYY-MM-DD&to=YYYY-MM-DD&group=weekly&format=json|csv&client_id=`. Включительные локальные дни; group weekly optional (ISO Monday). Customer собственные расчеты, courier своя смена, cashier своя касса, accountant/admin финансовый scope. JSON `{from,to,generated_at,totals,items}`; CSV UTF-8 с source IDs,event_at,business_date,client_id,order_id,kind,amount,status. Pending не считается paid; user text с =,+,-,@ безопасно экранируется. Недельный scheduled export использует тот же запрос, не отдельную арифметику.

## Граница готовности

Каждый описанный route считается реализованным только после проверки маршрутизации, ролей и инвариантов. Если интерфейс реализации отличается, backend/frontend синхронно обновляют этот файл. Необязательные дополнительные endpoints не заменяют обязательную бизнес-семантику. Недостающие route/правило явно заносятся в mvp-plan.md и итоговый отчет; отсутствие проверок не обозначается PASS.

