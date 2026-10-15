import { t } from './preferences';
import React, { useEffect, useState } from 'react';
import { ErrorBox, useCollection, useOperations, money } from './workspace';
import { ApiError } from './api';
import { reconcileCart } from './cart';
export function AdminOrder({ op }: {
    op: ReturnType<typeof useOperations>;
}) {
    const clients = useCollection('/clients'), [client, setClient] = useState(''), [date, setDate] = useState(new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' })), [quantities, setQuantities] = useState<Record<string, number>>({});
    const [catalogRevision,setCatalogRevision]=useState(0),[priceReview,setPriceReview]=useState(false),[accepted,setAccepted]=useState(false);
    const points = useCollection('/delivery-points' + (client ? '?client_id=' + client : '')), catalog = useCollection('/catalog?delivery_date=' + date,catalogRevision);
    useEffect(()=>{if(!priceReview||catalog.loading||catalog.error)return;if(catalog.nextCursor){void catalog.loadMore();return}setQuantities(old=>reconcileCart(catalog.items,old,date!==new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Almaty'})).quantities)},[priceReview,catalog.loading,catalog.payload,catalog.nextCursor]);
    return <details className="card">
    <summary>{t("Новый заказ для клиента")}</summary>
    <ErrorBox error={clients.error || points.error || catalog.error}/>
    <form onSubmit={async (e) => { e.preventDefault(); if(priceReview&&!accepted)return;const form = e.currentTarget, f = new FormData(form); try {
            await op.act('/orders', { client_id: client, kind: date === new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' }) ? 'regular' : 'preorder', delivery_point_id: f.get('delivery_point_id'), requested_delivery_at: date + 'T' + f.get('time') + ':00+05:00', payment_mode: f.get('payment_mode'), items: catalog.items.filter(p => quantities[p.id] > 0).map(p => ({ product_id: p.id, quantity: quantities[p.id], expected_unit_price: p.price_amount })) });
            setQuantities({});
            setPriceReview(false);setAccepted(false);
            form.reset();
        }
        catch (error) { if(error instanceof ApiError&&error.code==='PRICE_CHANGED'){setPriceReview(true);setAccepted(false);setCatalogRevision(value=>value+1)} } }}>
 <label>{t("Клиент")}<select required value={client} onChange={e => setClient(e.target.value)}>
    <option value="">{t("Выберите клиента")}</option>
        {clients.items.map(c => <option key={c.id} value={c.id}>
        {c.name}
        </option>)}
    </select>
    </label>
 <label>{t("Адрес доставки")}<select name="delivery_point_id" required>
    <option value="">{t("Выберите адрес")}</option>
        {points.items.filter(p => p.client_id === client).map(p => <option key={p.id} value={p.id}>
        {p.address} · {p.recipient}
        </option>)}
    </select>
    </label>
 <div className="form-row">
    <label>{t("Дата")}<input type="date" required value={date} onChange={e => { setDate(e.target.value); setQuantities({});setPriceReview(false);setAccepted(false); }}/>
    </label>
    <label>{t("Время")}<input name="time" type="time" required defaultValue="12:00"/>
    </label>
    <label>{t("Способ оплаты")}<select name="payment_mode">
    <option value="deferred">{t("Отсрочка")}</option>
    <option value="kaspi">Kaspi</option>
    <option value="cash">{t("Наличные")}</option>
    </select>
    </label>
    </div>
 {catalog.items.filter(p => p.active !== false).map(p => <label key={p.id}>
        {p.name} · {money(p.price_amount)}<input type="number" min="0" value={quantities[p.id] || ''} onChange={e => {setQuantities({ ...quantities, [p.id]: Number(e.target.value) });setAccepted(false)}}/>
        </label>)}{catalog.nextCursor&&<button type="button" disabled={catalog.loading} onClick={()=>catalog.loadMore()}>{t('Показать ещё')}</button>}{priceReview&&<div className="notice" role="alert"><p>{t('Цены изменились. Каталог и корзина обновлены.')}</p><p>{t('Новая сумма')}: {money(catalog.items.reduce((sum,p)=>sum+Number(p.price_amount)*(quantities[p.id]||0),0))}</p><label className="checkbox-label"><input type="checkbox" checked={accepted} disabled={catalog.loading||!!catalog.error} onChange={e=>setAccepted(e.target.checked)}/>{t('Подтверждаю новую сумму заказа')}</label></div>}<button className="primary" disabled={op.busy || catalog.loading || !client || !Object.values(quantities).some(n => n > 0)||(priceReview&&!accepted)}>{t("Создать заказ")}</button>
    </form>
    </details>;
}
