import React, { useEffect, useId, useRef, useState } from 'react';
import { apiRequest, ApiError } from './api';
import { ErrorBox, money, useCollection, useOperations } from './workspace';
import { t } from './preferences';

type DraftRow = { source_text: string; product_id: string | null; quantity: string | null; unit: string | null; issues: string[] };
type Draft = { items: DraftRow[]; delivery_date: string | null; questions: string[] };
type Row = { source: string; product: string; quantity: string; issues: string[] };
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' });

export function AIOrder({ op }: { op: ReturnType<typeof useOperations> }) {
    const [open, setOpen] = useState(false), [created, setCreated] = useState(false);
    return <section className="card ai-order">
        <div className="ai-order-heading"><div><h2>{t('Заказ из сообщения')}</h2><p className="muted">{t('Сначала проверьте черновик. Товар резервируется только при создании заказа.')}</p></div>
            {!open && <button onClick={() => { setCreated(false); setOpen(true); }}>{t('Создать заказ из сообщения')}</button>}</div>
        {created && <p role="status" className="notice">{t('Заказ создан.')}</p>}
        {open && <DraftForm op={op} close={() => setOpen(false)} success={() => { setOpen(false); setCreated(true); }}/>}
    </section>;
}

function DraftForm({ op, close, success }: { op: ReturnType<typeof useOperations>; close: () => void; success: () => void }) {
    const id = useId(), clients = useCollection('/clients');
    const [client, setClient] = useState(''), [message, setMessage] = useState(''), [day, setDay] = useState('');
    const [time, setTime] = useState(''), [point, setPoint] = useState(''), [payment, setPayment] = useState('');
    const [rows, setRows] = useState<Row[]>([]), [questions, setQuestions] = useState<string[]>([]);
    const [enabled, setEnabled] = useState(false), [checking, setChecking] = useState(true), [parsing, setParsing] = useState(false), [saving, setSaving] = useState(false);
    const [reviewed, setReviewed] = useState(false), [aiUsed, setAIUsed] = useState(false), [error, setError] = useState<unknown>(null), [replace, setReplace] = useState(false);
    const [catalogRevision, setCatalogRevision] = useState(0);
    const mounted = useRef(true), generation = useRef(0), controller = useRef<AbortController | null>(null), submitting = useRef(false);
    const points = useCollection(client ? '/delivery-points?client_id=' + client : '');
    const catalog = useCollection('/catalog?delivery_date=' + (day || today()), catalogRevision);
    const prices = catalog.items.map(p => p.id + ':' + p.price_amount + ':' + p.active).join('|');
    useEffect(() => { setReviewed(false); }, [prices]);
    useEffect(() => { if (catalog.nextCursor && !catalog.loading && !catalog.error) void catalog.loadMore(); }, [catalog.nextCursor, catalog.loading]);
    useEffect(() => {
        mounted.current = true;
        apiRequest('/ai/status').then(result => { if (mounted.current) setEnabled(result.enabled === true); }).catch(() => {}).finally(() => { if (mounted.current) setChecking(false); });
        return () => { mounted.current = false; generation.current++; controller.current?.abort(); };
    }, []);
    function invalidate() { generation.current++; controller.current?.abort(); setParsing(false); setReviewed(false); setReplace(false); }
    function update(index: number, change: Partial<Row>) { invalidate(); setRows(old => old.map((row, i) => i === index ? { ...row, ...change } : row)); }
    async function parse() {
        if (!enabled || parsing || !client || !message.trim() || message.length > 4000) return;
        if (rows.length && !replace) { setReplace(true); return; }
        const current = ++generation.current;
        controller.current?.abort(); controller.current = new AbortController();
        setParsing(true); setError(null); setReplace(false); setReviewed(false);
        try {
            // Never use useOperations here: its retry cache is only for confirmed mutations.
            const result = await apiRequest<Draft>('/ai/order-draft', { method: 'POST', body: JSON.stringify({ client_id: client, message }), signal: controller.current.signal });
            if (!mounted.current || current !== generation.current) return;
            if (!Array.isArray(result.items) || result.items.length > 20 || !Array.isArray(result.questions)) throw new Error(t('Не удалось разобрать сообщение. Исправьте черновик вручную.'));
            setRows(result.items.map(row => ({ source: row.source_text, product: row.product_id || '', quantity: row.quantity || '', issues: row.issues })));
            setDay(result.delivery_date || ''); setQuestions(result.questions); setAIUsed(true);
        } catch (failure) { if (mounted.current && current === generation.current) setError(failure); }
        finally { if (mounted.current && current === generation.current) setParsing(false); }
    }
    const validRows = rows.length > 0 && rows.every(row => /^\d+(?:\.0+)?$/.test(row.quantity) && Number(row.quantity) >= 1 && Number(row.quantity) <= 10000 && catalog.items.some(p => p.id === row.product && p.active !== false));
    const allResolved = client && point && day >= today() && time && payment && validRows && !catalog.loading && !catalog.error && !catalog.nextCursor && !points.loading && !points.error && new Set(rows.map(row => row.product)).size === rows.length;
    return <form className="ai-order-form" onSubmit={async event => {
        event.preventDefault();
        if (!allResolved || !reviewed || submitting.current) return;
        submitting.current = true; setSaving(true); setError(null);
        try {
            await op.act('/orders', { client_id: client, kind: day === today() ? 'regular' : 'preorder', delivery_point_id: point, requested_delivery_at: `${day}T${time}:00+05:00`, payment_mode: payment, ai_used: aiUsed,
                items: rows.map(row => ({ product_id: row.product, quantity: Number(row.quantity), expected_unit_price: catalog.items.find(p => p.id === row.product)!.price_amount })) });
            setMessage(''); setRows([]); setQuestions([]); success();
        } catch (failure) { if (mounted.current) { setError(failure); setReviewed(false); if (failure instanceof ApiError && failure.code === 'PRICE_CHANGED') setCatalogRevision(value => value + 1); } }
        finally { submitting.current = false; if (mounted.current) setSaving(false); }
    }}>
        <div className="ai-order-toolbar"><label>{t('Клиент')}<select required value={client} disabled={saving} onChange={event => { invalidate(); if (client) { setMessage(''); setRows([]); setQuestions([]); setAIUsed(false); } setClient(event.target.value); setPoint(''); }}>
            <option value="">{t('Выберите клиента')}</option>{clients.items.filter(c => c.approval_status === 'active' && !c.archived).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></label>{clients.nextCursor && <button type="button" disabled={clients.loading} onClick={() => clients.loadMore()}>{t('Показать ещё')}</button>}
        <button type="button" disabled={saving} onClick={close}>{t('Закрыть черновик')}</button></div>
        <ErrorBox error={error || clients.error || points.error || catalog.error}/>
        <div className="ai-draft-columns">
            <section className="ai-draft-source" aria-labelledby={id + '-source'}><h3 id={id + '-source'}>{t('1. Сообщение')}</h3>
                <label htmlFor={id + '-message'}>{t('Сообщение клиента')}</label>
                <textarea id={id + '-message'} value={message} maxLength={4000} rows={8} disabled={saving} autoComplete="off" spellCheck={false} aria-describedby={id + '-privacy'} onChange={event => { invalidate(); setMessage(event.target.value); }}/>
                <p className="muted" id={id + '-privacy'}>{t('Текст хранится только в открытой форме и удаляется после создания заказа или закрытия.')}</p>
                <p className="muted">{message.length} / 4000</p>
                {!enabled && !checking && <p className="notice" role="status">{t('ИИ пока не подключён. Заполните черновик вручную.')}</p>}
                <button type="button" disabled={!enabled || checking || parsing || saving || !client || !message.trim()} onClick={() => void parse()}>{t(parsing ? 'Разбираем сообщение…' : 'Разобрать сообщение')}</button>
                {replace && <div className="notice" role="alert"><p>{t('Новый разбор заменит исправленные позиции и дату. Продолжить?')}</p><button type="button" onClick={() => void parse()}>{t('Заменить черновик')}</button><button type="button" onClick={() => setReplace(false)}>{t('Отмена')}</button></div>}
            </section>
            <section aria-labelledby={id + '-review'}><h3 id={id + '-review'}>{t('2. Проверка заказа')}</h3>
                {questions.length > 0 && <div className="notice"><strong>{t('Требуют уточнения')}</strong><ul>{questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div>}
                {!rows.length && <p className="muted">{t('Здесь появятся позиции. Их также можно добавить вручную.')}</p>}
                {rows.map((row, i) => <fieldset className="ai-draft-row" key={i} disabled={saving}><legend>{t('Позиция')} {i + 1}</legend>
                    {row.source && <p className="ai-source-fragment">{row.source}</p>}
                    <label>{t('Товар')} {i + 1}<select required value={row.product} onChange={event => update(i, { product: event.target.value })}><option value="">{t('Выберите товар')}</option>{catalog.items.filter(p => p.active !== false).map(p => <option key={p.id} value={p.id}>{p.name} · {money(p.price_amount)}</option>)}</select></label>
                    <label>{t('Количество')} {i + 1}<input required type="number" min="1" max="10000" step="1" value={row.quantity} onChange={event => update(i, { quantity: event.target.value })}/></label>
                    {row.issues.map((issue, n) => <p className="muted" key={n}>{issue}</p>)}
                    <button type="button" onClick={() => { invalidate(); setRows(old => old.filter((_, n) => i !== n)); }}>{t('Удалить позицию')}</button>
                </fieldset>)}
                <button type="button" disabled={rows.length >= 20 || saving} onClick={() => { invalidate(); setRows(old => [...old, { source: '', product: '', quantity: '', issues: [] }]); }}>{t('Добавить позицию')}</button>
                <div className="form-grid">
                    <label>{t('Дата доставки')}<input required type="date" min={today()} value={day} disabled={saving} onChange={event => { invalidate(); setDay(event.target.value); }}/></label>
                    <label>{t('Время доставки')}<input required type="time" value={time} disabled={saving} onChange={event => { invalidate(); setTime(event.target.value); }}/></label>
                    <label>{t('Адрес доставки')}<select required value={point} disabled={!client || saving} onChange={event => { invalidate(); setPoint(event.target.value); }}><option value="">{t('Выберите адрес')}</option>{points.items.filter(p => p.client_id === client).map(p => <option key={p.id} value={p.id}>{p.address}</option>)}</select></label>
                    {points.nextCursor && <button type="button" onClick={() => points.loadMore()}>{t('Показать ещё')}</button>}
                    <label>{t('Способ оплаты')}<select required value={payment} disabled={saving} onChange={event => { invalidate(); setPayment(event.target.value); }}><option value="">{t('Выберите способ оплаты')}</option><option value="deferred">{t('Отсрочка')}</option><option value="cash">{t('Наличные')}</option><option value="kaspi">Kaspi</option></select></label>
                </div>
                <label className="checkbox-label"><input type="checkbox" checked={reviewed} disabled={!allResolved || parsing || saving} onChange={event => setReviewed(event.target.checked)}/>{t('Проверил товары, количество, дату, адрес и условия оплаты')}</label>
                <button className="primary" disabled={!allResolved || !reviewed || parsing || saving || op.busy}>{t(saving ? 'Создаём заказ…' : 'Создать заказ')}</button>
            </section>
        </div>
    </form>;
}
