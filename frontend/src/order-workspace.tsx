import { t, locale } from './preferences';
import React, { useState } from 'react';
import { ErrorBox, FieldsForm, PhotoUpload, useCollection, useOperations, money, status } from './workspace';
import { OrderEvidence } from './account-features';
import { CustomerOrderActions } from './customer';
export function OrderPanel({ order: o, role, op, close }: {
    order: any;
    role: string;
    op: ReturnType<typeof useOperations>;
    close: () => void;
}) {
    const [photoIds, setPhotoIds] = useState<string[]>([]), [quantities, setQuantities] = useState<Record<string, number>>({}), [cash, setCash] = useState(''), [reason, setReason] = useState(''), [change, setChange] = useState(''), [consent, setConsent] = useState(false);
    const transitions: Record<string, string> = { submitted: 'accepted', accepted: 'preparing', preparing: 'ready', ready: 'out_for_delivery', delivery_failed: 'out_for_delivery' };
    return <section className="card">
    <div className="section-title">
    <h2>{t("Заказ №")}{o.id.slice(0, 8)}
    </h2>
    <button onClick={close}>{t("Закрыть")}</button>
    </div>
    <p>
    {status(o.status)} · {status(o.payment_mode)} · {money(o.total_amount)}{o.payment_status&&<> · {status(o.payment_status)}</>}
    </p>
    {o.status==="delivered"||Number(o.delivered_total_amount||0)>0?<p>{t("К погашению:")}{' '}<strong className={`debt-value${Number(o.outstanding_amount) > 0 ? ' positive' : ''}`}>{money(o.outstanding_amount)}</strong>{' '}{t("· Стоимость после возвратов:")}{' '}{money(o.settlement_amount??o.total_amount)}</p>:<p className="muted">{t("Задолженность начисляется после передачи товара.")}</p>}<p>
    {typeof o.address_snapshot === 'object' ? Object.values(o.address_snapshot || {}).filter(x => typeof x === 'string').join(', ') : o.address_snapshot || o.delivery_address || o.delivery_point?.address || ''}
    </p>
        {o.items?.map((i: any) => <div className="order-row" key={i.product_id}>
        <span>
        {i.name || i.product_id} × {i.quantity}
        </span>
        <strong>
        {money(i.line_total_amount)}
        </strong>
        </div>)}<OrderEvidence order={o}/>{role==='courier'&&['delivered','partially_delivered'].includes(o.status)&&<CustomerOrderActions order={o} onChanged={op.refresh} returnsOnly/>}{role === 'admin' && <>
        <FieldsForm title={t("Изменить состояние")} fields={[{ name: 'status', label: 'Следующий этап', options: Object.entries(transitions).filter(([s]) => s === o.status).map(([, s]) => [s, status(s)]).concat([['cancelled', 'Отменить']]) }, { name: 'courier_id', label: 'Курьер (для выезда)', required: false }, { name: 'reason', label: 'Причина / комментарий', required: false }]} onSubmit={d => op.act('/orders/' + o.id + '/transition', { ...d, courier_id: d.courier_id || undefined, version: o.version })} busy={op.busy}/>
        {o.kind === 'preorder' && <Fulfill order={o} op={op}/>}<FieldsForm title={t("Одобрить отсрочку вместо наличных")} fields={[{ name: "reason", label: "Основание изменения способа расчёта" }]} onSubmit={d => op.act("/orders/" + o.id + "/payment-mode", { ...d, payment_mode: "deferred", version: o.version })} busy={op.busy}/>
        <FieldsForm title={t("Предложить перенос")} fields={[{ name: 'requested_delivery_at', label: 'Дата и время', type: 'datetime-local' }, { name: 'reason', label: 'Причина' }]} onSubmit={d => op.act('/orders/' + o.id + '/reschedule', { ...d, requested_delivery_at: new Date(d.requested_delivery_at).toISOString(), version: o.version })} busy={op.busy}/>
        </>}{['courier','admin'].includes(role) && ['out_for_delivery', 'dispatched'].includes(o.status) && <form onSubmit={async (e) => {
                e.preventDefault();
                try {
                    await op.act('/orders/' + o.id + '/delivery', { version: o.version, items: o.items.map((i: any) => ({ product_id: i.product_id, quantity: quantities[i.product_id] ?? i.quantity })), photo_ids: photoIds, cash_received_amount: cash || '0', cash_change_amount: change || '0', advance_consent: consent, reason });
                    close();
                }
                catch { }
            }}>
        <h3>{t("Фактическая передача")}</h3>
            {o.items?.map((i: any) => <label key={i.product_id}>
            {i.name || i.product_id}{' '}{t("— принято порций")}<input type="number" min="0" max={i.quantity} value={quantities[i.product_id] ?? i.quantity} onChange={e => setQuantities({ ...quantities, [i.product_id]: Number(e.target.value) })}/>
            </label>)}<label>{t("Получено наличными, KZT")}<input type="number" min="0" step="0.01" value={cash} onChange={e => setCash(e.target.value)}/>
        </label>
        <label>{t("Выдана сдача, KZT")}<input type="number" min="0" step="0.01" value={change} onChange={e => setChange(e.target.value)}/>
        </label>
        <label className="checkbox-label">
        <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>{t("Клиент согласен зачислить переплату в аванс")}</label>
        <label>{t("Комментарий / причина частичной передачи")}<textarea value={reason} onChange={e => setReason(e.target.value)}/>
        </label>
        <PhotoUpload orderId={o.id} purpose="delivery" onUploaded={id => setPhotoIds(p => [...p, id])} act={op.act} busy={op.busy}/>
        <button className="primary" disabled={op.busy || !photoIds.length || (role==="admin"&&!reason)}>{t("Подтвердить передачу")}</button>
        <button type="button" disabled={op.busy || !reason} onClick={() => op.act('/orders/' + o.id + '/delivery-failed', { reason, version: o.version }).then(close).catch(() => { })}>{t("Не удалось вручить")}</button>
        </form>}
    {role === 'admin' && <>
        <FieldsForm title={t("Назначить сбор оплаты по доставленному заказу")} fields={[{ name: 'courier_id', label: 'Курьер' }, { name: 'reason', label: 'Основание' }]} onSubmit={d => op.act('/orders/' + o.id + '/assign-collection', d)} busy={op.busy}/>
        {['delivery_failed', 'delivered', 'partially_delivered'].includes(o.status) && <GoodsReturn order={o} op={op}/>}
        </>}
    {role === 'courier' && o.status === 'ready' && <button className="primary" disabled={op.busy} onClick={() => op.act('/orders/' + o.id + '/transition', { status: 'out_for_delivery', version: o.version }).catch(() => { })}>{t("Выехать на доставку")}</button>}
    {role === 'courier' && o.status === 'delivered' && <CashCollection order={o} op={op}/>}
    </section>;
}
function Fulfill({ order, op }: {
    order: any;
    op: ReturnType<typeof useOperations>;
}) {
    const batches = useCollection('/batches', op.revision), [qty, setQty] = useState<Record<string, number>>({});
    function quantity(batch: any, item: any) { if (qty[batch.id] !== undefined)
        return qty[batch.id]; const first = batches.items.find(b => b.product_id === item.product_id && b.quantity - b.reserved >= item.quantity && new Date(b.expires_at) > new Date()); return first?.id === batch.id ? item.quantity : 0; }
    return <form className="compact-form" onSubmit={async (e) => { e.preventDefault(); const rows = order.items.flatMap((i: any) => batches.items.filter(b => b.product_id === i.product_id && quantity(b, i) > 0).map(b => ({ product_id: i.product_id, batch_id: String(b.id), quantity: quantity(b, i) }))); try {
            await op.act('/orders/' + order.id + '/fulfill', { version: order.version, batches: rows });
        }
        catch { } }}>
    <h3>{t("Обеспечить весь предзаказ готовыми партиями")}</h3>
    <p>{t("Укажите распределение по партиям. Каждая позиция должна быть обеспечена полностью.")}</p>
    <ErrorBox error={batches.error}/>
        {order.items.map((i: any) => <fieldset key={i.product_id}>
        <legend>
        {i.name} — {t('Требуется {{count}} порций', { count: i.quantity })}</legend>
            {batches.items.filter(b => b.product_id === i.product_id && b.quantity > b.reserved && new Date(b.expires_at) > new Date()).map(b => <label key={b.id}>{t('Изготовлено {{date}} · свободно {{count}}', { date: new Date(b.manufactured_at).toLocaleString(locale(), { timeZone: 'Asia/Almaty' }), count: b.quantity - b.reserved })}<input type="number" min="0" max={b.quantity - b.reserved} value={quantity(b, i)} onChange={e => setQty({ ...qty, [b.id]: Number(e.target.value) })}/>
            </label>)}
        </fieldset>)}<button className="primary" disabled={op.busy}>{t("Подтвердить производство и резерв")}</button>
    </form>;
}
function GoodsReturn({ order, op }: {
    order: any;
    op: ReturnType<typeof useOperations>;
}) {
    const [qty, setQty] = useState<Record<string, number>>({});
    return <form onSubmit={async (e) => { e.preventDefault(); const f = new FormData(e.currentTarget); try {
            await op.act('/orders/' + order.id + '/goods-return', { reason: f.get('reason'), items: order.items.filter((i: any) => qty[i.product_id] > 0).map((i: any) => ({ product_id: i.product_id, quantity: qty[i.product_id] })) });
        }
        catch { } }}>
    <h3>{t("Принять недоставленный товар в карантин")}</h3>
        {order.items.filter((i: any) => i.quantity > (i.delivered_quantity || 0)).map((i: any) => <label key={i.product_id}>
        {i.name}<input type="number" min="0" max={i.quantity - (i.delivered_quantity || 0)} value={qty[i.product_id] || ''} onChange={e => setQty({ ...qty, [i.product_id]: Number(e.target.value) })}/>
        </label>)}<label>{t("Причина")}<input name="reason" required/>
    </label>
    <button disabled={op.busy || !Object.values(qty).some(n => n > 0)}>{t("Подтвердить физический приём")}</button>
    </form>;
}
function CashCollection({ order, op }: {
    order: any;
    op: ReturnType<typeof useOperations>;
}) {
    const [photos, setPhotos] = useState<string[]>([]);
    return <form onSubmit={async (e) => { e.preventDefault(); const f = new FormData(e.currentTarget); try {
            await op.act('/payments', { client_id: order.client_id, order_id: order.id, method: 'cash', amount: f.get('amount'), photo_ids: photos });
            setPhotos([]);
        }
        catch { } }}>
    <h3>{t("Принять наличные в счёт задолженности")}</h3>
    <label>{t("Сумма KZT")}<input name="amount" type="number" min="0.01" step="0.01" required/>
    </label>
    <PhotoUpload orderId={order.id} purpose="cash" onUploaded={id => setPhotos(p => [...p, id])} act={op.act} busy={op.busy}/>
    <button className="primary" disabled={op.busy || !photos.length}>{t("Зафиксировать оплату")}</button>
    </form>;
}

