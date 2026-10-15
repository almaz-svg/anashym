import { t, locale } from './preferences';
import React, { createContext, useContext, useEffect, useId, useRef, useState } from 'react';
import { apiRequest, ApiError, isDefinitiveFailure } from './api';
export const money = (v: any) => new Intl.NumberFormat(locale(), { style: 'currency', currency: 'KZT', maximumFractionDigits: 2 }).format(Number(v || 0));
export const WorkspaceRevision = createContext(0);
const fieldLabels: Record<string, string> = { amount: 'Сумма', reason: 'Причина', phone: 'Телефон', password: 'Пароль', name: 'Название', description: 'Описание', category: 'Категория', category_other: 'Уточнение категории', expected_order_quantity: 'Порций за заказ', expected_order_frequency: 'Частота заказов', items: 'Позиции заказа', delivery_point_id: 'Адрес доставки', requested_delivery_at: 'Дата доставки', client_id: 'Клиент', order_id: 'Заказ', product_id: 'Товар', courier_id: 'Курьер', batch_id: 'Партия', quantity: 'Количество', reference: 'Номер перевода / комментарий', photo_ids: 'Фото подтверждения', from: 'Начало периода', to: 'Конец периода', credit_limit: 'Лимит отсрочки', credit_limit_amount: 'Лимит отсрочки', period_days: 'Период отсрочки', non_field_errors: 'Проверьте данные' };
export function ErrorBox({ error }: {
    error: unknown;
}) {
    return error ? <div role="alert" className="error">
    {t(error instanceof Error ? error.message : 'Не удалось выполнить запрос')}{error instanceof ApiError && Object.entries(error.field_errors).map(([k, v]) => <p key={k}>
        {t(fieldLabels[k] || 'Проверьте данные')}: {v.map(message => t(message)).join(' ')}
        </p>)}
    </div> : null;
}
export function useOperations() {
    const [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [revision, setRevision] = useState(0);
    const attempts = useRef(new Map<string, string>());
    async function act(path: string, body: any, method = 'POST') {
        setBusy(true);
        setError(null);
        const fingerprint = path + (body instanceof FormData ? JSON.stringify([...body.entries()].map(([k, v]) => [k, v instanceof File ? { name: v.name, size: v.size, type: v.type, modified: v.lastModified } : v])) : JSON.stringify(body));
        let key = attempts.current.get(fingerprint);
        if (!key) {
            key = crypto.randomUUID();
            attempts.current.set(fingerprint, key);
        }
        try {
            const result = await apiRequest(path, { method, body: body instanceof FormData ? body : JSON.stringify(body), headers: { 'Idempotency-Key': key } });
            attempts.current.delete(fingerprint);
            setRevision(r => r + 1);
            window.dispatchEvent(new Event('bakery:data-changed'));
            return result;
        }
        catch (e) {
            setError(e);
            if (isDefinitiveFailure(e))
                attempts.current.delete(fingerprint);
            throw e;
        }
        finally {
            setBusy(false);
        }
    }
    return { error, setError, busy, revision, act, refresh: () => setRevision(r => r + 1) };
}
export function useCollection(path:string,revision=0){
 const workspaceRevision=useContext(WorkspaceRevision);
 const [items,setItems]=useState<any[]>([]),[error,setError]=useState<unknown>(null),[loading,setLoading]=useState(true),[payload,setPayload]=useState<any>(null),[nextCursor,setNextCursor]=useState<string|null>(null);
 const generation=useRef(0),inFlight=useRef(false);
 async function requestPage(append:boolean,version:number,cursor?:string|null){
  if(append&&inFlight.current)return;inFlight.current=true;setLoading(true);setError(null);
  try{const r=await apiRequest(path+(append&&cursor?(path.includes('?')?'&':'?')+'cursor='+encodeURIComponent(cursor):''));if(version!==generation.current)return;setItems(old=>append?[...old,...(r.items||[]).filter((x:any)=>!old.some(y=>y.id&&y.id===x.id))]:r.items||[]);setPayload(r);setNextCursor(r.next_cursor||null)}catch(e){if(version===generation.current)setError(e)}finally{if(version===generation.current){inFlight.current=false;setLoading(false)}}
 }
 useEffect(()=>{const version=++generation.current;inFlight.current=false;setItems([]);setPayload(null);setNextCursor(null);if(path)void requestPage(false,version);else setLoading(false);return()=>{generation.current++;inFlight.current=false}},[path,revision,workspaceRevision]);
 return {items,error,loading,payload,nextCursor,loadMore:()=>requestPage(true,generation.current,nextCursor)};
}
export function FieldsForm({ title, fields, onSubmit, busy, submit = 'Сохранить' }: {
    title: string;
    fields: Field[];
    onSubmit: (data: any) => Promise<any>;
    busy?: boolean;
    submit?: string;
}) {
    const [references, setReferences] = useState<Record<string, any[]>>({}), [error, setError] = useState<unknown>(null), [result, setResult] = useState<any>(null);
    const formId = useId(), workspaceRevision = useContext(WorkspaceRevision);
    const resources: Record<string, string> = { product_id: '/products', batch_id: '/batches', courier_id: '/staff', user_id: '/staff', client_id: '/clients', order_id: '/orders' };
    const orderChoices=useCollection(fields.some(f=>f.name==='order_id')?'/orders?limit=20':'',0);
const needed = fields.filter(f => resources[f.name]&&f.name!=='order_id').map(f => f.name).join(',');
    useEffect(() => {
        let active = true;
        Promise.all(needed.split(',').filter(Boolean).map(async (name) => [name, (await apiRequest(resources[name])).items] as const)).then(rows => {
            if (active)
                setReferences(Object.fromEntries(rows));
        }).catch(e => {
            if (active)
                setError(e);
        });
        return () => { active = false; };
    }, [needed,workspaceRevision]);
    return <form className="card compact-form" onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const f = new FormData(form), data: any = {};
            fields.forEach(x => { const raw = f.get(x.name); data[x.name] = x.type === 'checkbox' ? f.has(x.name) : x.type === 'number' ? Number(raw) : raw; });
            setError(null); setResult(null);
            try {
                const response = await onSubmit(data);
                setResult(response?.invitation_token ? response : null);
                form.reset();
            }
            catch (failure) { setError(failure); }
        }}>
    <h2>
    {title}
    </h2>
    <ErrorBox error={error}/>
        {result && <p className="notice">{t("Приглашение создано. Код установки пароля:")}{' '}{result.invitation_token}
        </p>}<div className="form-grid">
        {fields.map(f => {
            const options = f.options || ((f.name==='order_id'?orderChoices.items:references[f.name])?.filter(x => f.name !== 'courier_id' || x.role === 'courier').filter(x => f.name !== 'product_id' || x.active !== false).map(x => [String(x.id), x.name || x.phone || (f.name === 'order_id' ? '№' + x.id.slice(0, 8) + ' · ' + status(x.status) + ' · ' + money(x.total_amount) : ((f.name === 'batch_id' ? t('Партия') + ' · ' : '') + (x.manufactured_at ? new Date(x.manufactured_at).toLocaleString(locale(), { timeZone: 'Asia/Almaty' }) : x.id.slice(0, 8)) + ' · ' + t('{{count}} порций', { count: x.quantity ?? '' })))]));
            const errors = error instanceof ApiError ? error.field_errors[f.name] : undefined;
            const accessible = { 'aria-invalid': errors?.length ? true as const : undefined, 'aria-describedby': errors?.length ? formId + '-' + f.name : undefined };
            return <label key={f.name} className={f.type === 'checkbox' ? 'checkbox-label' : undefined}>
            {t(f.label)}{f.type === 'checkbox' ? <input name={f.name} type="checkbox" defaultChecked={f.value === 'true'} {...accessible}/> : options ? <select name={f.name} required={f.required !== false} defaultValue={f.value || ''} {...accessible}>
                <option value="">{t("Выберите…")}</option>
                    {options.map(([v, optionText]) => <option value={v} key={v}>
                    {f.options ? t(optionText) : optionText}
                    </option>)}
                </select> : <input name={f.name} type={f.type || 'text'} required={f.required !== false} defaultValue={f.value} min={f.type === 'number' ? 0 : undefined} step={f.step} {...accessible}/>}
            {!!errors?.length && <small id={formId + '-' + f.name} className="field-error">{errors.map(message=>t(message)).join(' ')}</small>}
            </label>;
        })}
    </div>
    {fields.some(f=>f.name==='order_id')&&<><ErrorBox error={orderChoices.error}/>{orderChoices.nextCursor&&<button type='button' disabled={orderChoices.loading} onClick={()=>orderChoices.loadMore()}>{t("Показать ещё заказы для выбора")}</button>}</>}
    <button className="primary" disabled={busy}>
    {t(busy ? 'Сохраняем…' : submit)}
    </button>
    </form>;
}
export type Field = {
    name: string;
    label: string;
    type?: string;
    required?: boolean;
    value?: string;
    step?: string;
    options?: string[][];
};
const labels: Record<string, string> = { pending_review: 'Ожидает проверки', regular: 'Обычный заказ', preorder: 'Предзаказ', available: 'Доступен', admin:'Администратор',courier:'Курьер',cashier:'Кассир',accountant:'Бухгалтер',customer:'Заказчик',return:'Возврат',exchange:'Обмен',quarantine:'Карантин',write_off:'Списание',delivery:'Передача товара',payment:'Оплата',refund:'Возврат денег',issue:'Выдача подотчёта',handover:'Сдача в кассу',coffee_shop: 'Кофейня', store: 'Магазин', restaurant: 'Ресторан / кафе', company: 'Компания', individual: 'Частный покупатель', other: 'Другое', settled: 'Расчёты закрыты', paid: 'Оплачен', partial: 'Частично оплачен', unpaid: 'Не оплачен', submitted: 'На рассмотрении', accepted: 'Принят', preparing: 'Готовится', ready: 'Готов', out_for_delivery: 'В пути', dispatched: 'В пути', partially_delivered: 'Передан частично', active: 'Доступ открыт', delivered: 'Передан', cancelled: 'Отменён', delivery_failed: 'Не вручён', pending: 'Ожидает проверки', confirmed: 'Подтверждён', approved: 'Одобрен', rejected: 'Отклонён', open: 'Открыта', closed: 'Закрыта', kaspi: 'Kaspi', cash: 'Наличные', deferred: 'Отсрочка' };
Object.assign(labels,{reversed:'Сторнирован'});
export const status = (s: string) => labels[s] ? t(labels[s]) : s;
const frequencyLabels: Record<string, string> = { daily: 'Ежедневно', weekly: 'Раз в неделю', monthly: 'Раз в месяц', on_demand: 'По необходимости', 'Ежедневно': 'Ежедневно', 'Несколько раз в неделю': 'Несколько раз в неделю', 'Раз в неделю': 'Раз в неделю', 'По необходимости': 'По необходимости' };
export const orderFrequency = (value: string) => !value ? t('Не указана') : frequencyLabels[value] ? t(frequencyLabels[value]) : value;
const additionalRecordLabels: Record<string, string> = { total_amount: 'Итого', delivered_amount: 'Передано', delivered_total_amount: 'Передано', paid_amount: 'Подтверждённые оплаты', return_credit_amount: 'Зачтённые возвраты', refund_amount: 'Возвращено денег', outstanding_amount: 'Осталось оплатить', turnover_amount: 'Оборот', charged_amount: 'Начислено', credit_amount: 'Зачтённые возвраты', balance_amount: 'Баланс', net_amount: 'Изменение баланса', overdue_amount: 'Просрочено', unconfirmed_payment_amount: 'Ожидает подтверждения', available_credit_amount: 'Доступная отсрочка', credit_limit_amount: 'Лимит отсрочки', reserved_credit_amount: 'Зарезервировано', price_amount: 'Цена', unit_price_amount: 'Цена за порцию', line_total_amount: 'Сумма позиции', state: 'Состояние проверки', currency: 'Валюта', client_name: 'Заказчик', payment_mode: 'Способ оплаты' };
Object.assign(additionalRecordLabels,{actor_name:'Кто выполнил',confirmed_by_name:'Кто подтвердил',reversed_by_name:'Кто выполнил',product_name:'Товар',shelf_life_hours:'Срок хранения, часов',archived:'В архиве',reversal_reason:'Причина сторнирования',reversed_at:'Сторнировано',payment_due_at:'Срок оплаты',courier_name:'Курьер',cashier_name:'Кассир',author_name:'Кто выполнил'});
export function Records({ items, title }: {
    items: any[];
    title: string;
}) {
    return <section className="card">
    <h2>
    {title}
    </h2>
    {!items.length && <p>{t("Записей пока нет.")}</p>}<div className="record-list">
        {items.map((x, i) => <article className="record" key={x.id || i}>
            {Object.entries(x).filter(([k, v]) => {
                // The API retains compatibility aliases; show each financial
                // fact once while keeping fallback fields and distinct states.
                if (k === 'amount_amount' && x.amount != null) return false;
                if (k === 'state' && x.status != null && (v === x.status || (x.status === 'pending' && v === 'pending_review'))) return false;
                return !['password', 'photo_ids', 'client_id', 'order_id', 'actor_id', 'author_id', 'courier_id', 'payment_id', 'user_id', 'cash_holder_id','cashier_id','confirmed_by_id','product_id','batch_id','object_id','source_id','proof_id','reversed_by','confirmed_by','image_url','source_reference'].includes(k) && v !== null && typeof v !== 'object';
            }).map(([k, v]) => <div key={k}>
            <small>
            {t(additionalRecordLabels[k] || ({ advance_amount: 'Аванс', settlement_amount: 'Стоимость после возвратов', unallocated_amount: 'Нераспределённый аванс', start: 'Начало периода', end_exclusive: 'Конец периода', payment_status: 'Состояние оплаты', recipient:'Получатель',address:'Адрес',window_start:'Доставка с',window_end:'Доставка до',opening_amount:'Начальный остаток',confirmed_at:'Подтверждено',accepted_amount:'Принято в кассу',due_at:'Срок оплаты',current_outstanding_amount:'Осталось погасить',active:'Активен',credited:'Зачёт проведён',resolved:'Обработан',action:'Событие',expected_order_quantity:'Порций за заказ',expected_order_frequency:'Частота заказов',category_other:'Уточнение категории',id: 'Номер', status: 'Статус', amount: 'Сумма', amount_amount: 'Сумма', debt_amount: 'Долг', name: 'Имя', title: 'Событие', message: 'Сообщение', created_at: 'Дата', reason: 'Причина', method: 'Способ', reference: 'Референс', type: 'Операция', client_id: 'Клиент', order_id: 'Заказ', period_start: 'Начало периода', period_end_exclusive: 'Конец периода', read_at: 'Прочитано', credit_limit: 'Лимит отсрочки', balance: 'Баланс', reserved_credit: 'Резерв лимита', period_days: 'Период, дней', deferred_approved: 'Отсрочка одобрена', approval_status: 'Доступ', requested_period_days: 'Запрошено дней', preferred_payment_mode: 'Предпочтительная оплата', category: 'Категория', description: 'Описание', preparation_minutes: 'Подготовка, мин', price: 'Цена', manufactured_at: 'Изготовлено', expires_at: 'Годно до', quantity: 'Порций', reserved: 'Резерв', date: 'Дата', cutoff: 'Приём заявок до', received: 'Физически принят', disposition: 'Учёт товара', kind: 'Тип операции', read: 'Прочитано', expected_amount: 'Ожидается в кассе', counted_amount: 'Фактически в кассе', discrepancy: 'Расхождение', opened_at: 'Смена открыта', closed_at: 'Смена закрыта', role: 'Роль', phone: 'Телефон' } as any)[k] || k)}
            </small>
            <span className={['debt_amount', 'outstanding_amount', 'current_outstanding_amount', 'overdue_amount'].includes(k) ? `debt-value${Number(v) > 0 ? ' positive' : ''}` : undefined}>
            {k.endsWith('_amount') || ['amount', 'balance', 'price', 'credit_limit', 'reserved_credit', 'discrepancy'].includes(k) ? money(v) : ['status', 'state', 'method', 'approval_status', 'preferred_payment_mode', 'payment_mode', 'payment_status', 'category','role','kind','disposition'].includes(k) ? status(String(v)) : k === 'expected_order_frequency' ? orderFrequency(String(v)) : k==='action'?notificationText(String(v)):k === 'id' ? '№' + String(v).slice(0, 8) : k.endsWith('_at') ? new Date(String(v)).toLocaleString(locale(), { timeZone: 'Asia/Almaty' }) : ['date', 'start', 'end_exclusive', 'period_start', 'period_end_exclusive'].includes(k) ? new Date(String(v) + 'T00:00:00+05:00').toLocaleDateString(locale(), { timeZone: 'Asia/Almaty' }) : typeof v === 'boolean' ? t(v ? 'Да' : 'Нет') : String(v)}
            </span>
            </div>)}
        </article>)}
    </div>
    </section>;
}
export function PhotoUpload({ orderId, purpose, onUploaded, act, busy }: {
    orderId: string;
    purpose: string;
    onUploaded: (id: string) => void;
    act: (p: string, b: any) => Promise<any>;
    busy: boolean;
}) {
    const [preview, setPreview] = useState(''),[error,setError]=useState<unknown>(null);
    useEffect(() => () => {
        if (preview)
            URL.revokeObjectURL(preview);
    }, [preview]);
    return <label>{t("Обязательное фото подтверждения")}<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} required={!preview} onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file)
                return;
            setError(null);
            const form = new FormData();
            form.set('files', file);
            form.set('order_id', orderId);
            form.set('purpose', purpose);
            try {
                const upload = await act('/files', form);
                const r = upload.items[0];
                onUploaded(r.id);
                const info = await apiRequest('/files/' + r.id);
                const response = await fetch(info.url, { credentials: 'include' });
                if (!response.ok)
                    throw new Error(t('Не удалось открыть защищённое фото'));
                setPreview(URL.createObjectURL(await response.blob()));
            }
            catch (failure) { setError(failure); }
        }}/>
    {preview && <img className="photo-proof" src={preview} alt={t("Загруженное подтверждение")}/>}
    <ErrorBox error={error}/>
    </label>;
}
const notificationLabels: Record<string, string> = { 'order.created': 'Заказ создан', 'order.accepted': 'Заказ принят', 'order.preparing': 'Заказ готовится', 'order.ready': 'Заказ готов к доставке', 'order.out_for_delivery': 'Курьер выехал', 'order.dispatched': 'Курьер выехал', 'order.delivery': 'Передача товара подтверждена', 'order.delivered': 'Заказ передан', 'order.cancelled': 'Заказ отменён', 'order.expired': 'Резерв истёк, заказ отменён', 'order.delivery_failed': 'Доставка не состоялась', 'order.fulfilled': 'Предзаказ обеспечен продукцией', 'order.reschedule_requested': 'Предложен перенос доставки', 'order.rescheduled': 'Перенос доставки подтверждён', 'payment.created': 'Заявка на оплату отправлена', 'payment.confirmed': 'Оплата подтверждена', 'payment.rejected': 'Заявка на оплату отклонена', 'ledger.delivery': 'Начислена стоимость переданного товара', 'ledger.payment': 'Поступила оплата', 'ledger.return': 'Зачтена стоимость возврата', 'ledger.refund': 'Оформлен возврат денег', 'return.requested': 'Запрошен возврат или обмен', 'return.received': 'Возврат физически принят', 'return.approved': 'Возврат одобрен', 'return.rejected': 'Возврат отклонён', 'refund.created': 'Создано обязательство возврата денег', 'refund.confirmed': 'Возврат денег подтверждён', 'client.approved': 'Условия клиента обновлены' };
Object.assign(notificationLabels,{'debt.overdue':'Задолженность просрочена','payment.reversed':'Оплата сторнирована'});
export const notificationText = (code: string) => notificationLabels[code] ? t(notificationLabels[code]) : (/^[a-z_]+\.[a-z_]+$/.test(code) ? t('Обновлены данные операции') : code);
