import { t, locale } from './preferences';
import React, { useState, useEffect } from 'react';
import { apiRequest } from './api';
import { PaymentFinancialSummary } from './customer-profile';
import { ErrorBox, FieldsForm, Records, useCollection, useOperations, PhotoUpload, money, status, notificationText } from './workspace';
import { NotificationMessage, ProtectedPhoto } from './account-features';
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' });
export function RefundObligations({revision=0}:{revision?:number}) {
 const data=useCollection('/refunds',revision);
 return <section className="refund-obligations"><ErrorBox error={data.error}/>{!!data.items.length&&<><p className="notice">{t('Возврат предоплаты после отмены отражается как обязательство. Деньги возвращены только после подтверждения операции.')}</p><Records items={data.items} title={t('Обязательства возврата')}/></>}{data.nextCursor&&<button onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}</section>;
}
export function KaspiPayment({op,order}:{op:ReturnType<typeof useOperations>;order?:any}) {
 const instructions=useCollection('/payment-instructions'),orders=useCollection(order?'':'/orders?limit=20'),[orderId,setOrderId]=useState(order?.id||''),[proof,setProof]=useState<string|null>(null),[done,setDone]=useState(false),[uploadRevision,setUploadRevision]=useState(0);
 return <section className="card"><h2>{t('Оплата продавцу через Kaspi')}</h2><p>{t('Оплатите заказ у продавца в Kaspi. Затем приложите квитанцию: сотрудник сверит поступление и подтвердит оплату.')}</p><ErrorBox error={instructions.error||orders.error}/>
 {instructions.payload?.configured&&instructions.payload.seller_url?<a className="primary" href={instructions.payload.seller_url} target="_blank" rel="noreferrer">{t('Перейти к продавцу в Kaspi')}</a>:<p className="notice">{t('Запросите у продавца ссылку или счёт Kaspi. После оплаты приложите квитанцию к заказу.')}</p>}
 <form onSubmit={async event=>{event.preventDefault();const form=event.currentTarget,data=new FormData(form);try{await op.act('/payments',{method:'kaspi',order_id:orderId,proof_id:proof,amount:data.get('amount'),reference:data.get('reference')});setDone(true);setProof(null);setUploadRevision(value=>value+1);form.reset()}catch{}}}>
 <label>{t('Заказ')}<select required value={orderId} disabled={!!order} onChange={e=>{setOrderId(e.target.value);setProof(null);setDone(false)}}><option value="">{t('Выберите…')}</option>{(order?[order]:orders.items).filter(o=>!['cancelled'].includes(o.status)).map(o=><option key={o.id} value={o.id}>№{o.id.slice(0,8)} · {money(o.total_amount)} · {status(o.status)}</option>)}</select></label>
 {orders.nextCursor&&<button type="button" disabled={orders.loading} onClick={()=>orders.loadMore()}>{t('Показать ещё заказы для выбора')}</button>}
 <div className="form-row"><label>{t('Сумма, KZT')}<input name="amount" type="number" min="0.01" step="0.01" required/></label><label>{t('Номер перевода / комментарий')}<input name="reference" required/></label></div>
 {orderId&&<PhotoUpload key={orderId+':'+uploadRevision} orderId={orderId} purpose="payment" onUploaded={id=>{setProof(id);setDone(false)}} act={op.act} busy={op.busy}/>}
 <ErrorBox error={op.error}/><button className="primary" disabled={op.busy||!orderId||!proof}>{t('Отправить на проверку')}</button>
 {done&&<p className="notice" role="status">{t('Квитанция отправлена. Ожидайте подтверждения сотрудника.')}</p>}
 </form></section>;
}
export function Payments() {
    const op = useOperations(), data = useCollection('/payments', op.revision);
    return <>
    <PaymentFinancialSummary revision={op.revision}/>
    <ErrorBox error={op.error || data.error}/>
    <KaspiPayment op={op}/>
    <p className="notice">{t("Заявка не погашает долг до подтверждения кассиром. Можно оплатить часть задолженности.")}</p>
    <Records items={data.items} title={t("История оплат")}/>
    {data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}
    <RefundObligations revision={op.revision}/>
    </>;
}
export function Reports({own=false}:{own?:boolean}) {
    const [from, setFrom] = useState(today()), [to, setTo] = useState(today()), [group, setGroup] = useState(''), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false);
    const archive = useCollection(!own&&group==='weekly'?'/weekly-reports':'');
    const data = useCollection('/reports?from=' + from + '&to=' + to + (group ? '&group=' + group : ''));
    async function download() {
        setBusy(true);
        setError(null);
        try {
            const response = await fetch('/api/v1/reports?from=' + from + '&to=' + to + '&format=csv' + (group ? '&group=' + group : '') + (data.payload?.cutoff ? '&cutoff=' + encodeURIComponent(data.payload.cutoff) : ''), { credentials: 'include' });
            if (!response.ok) {
                const e = await response.json();
                throw new Error(e.message || t('Отчёт недоступен'));
            }
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement('a');
            a.href = url;
            a.download = `report-${from}-${to}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        }
        catch (e) {
            setError(e);
        }
        finally {
            setBusy(false);
        }
    }
    return <>
    <section className="card">
    <h2>{t(own?'Мой отчёт':'Отчёт за период')}</h2>{own&&<p className="muted">{t('Показаны только ваши операции за выбранный период.')}</p>}
    <div className="form-row">
    <label>{t("С")}<input type="date" value={from} onChange={e => setFrom(e.target.value)}/>
    </label>
    <label>{t("По")}<input type="date" min={from} value={to} onChange={e => setTo(e.target.value)}/>
    </label>
    {!own&&<label>{t("Группировка")}<select value={group} onChange={e => setGroup(e.target.value)}>
    <option value="">{t("Операции")}</option>
    <option value="weekly">{t("Недельный архив")}</option>
    </select>
    </label>}
    </div>
    {group!=="weekly"&&<button onClick={download} disabled={busy || from > to || data.loading || !!data.error} className="primary">{t("Скачать CSV")}</button>}
    </section>
    <ErrorBox error={error || data.error}/>
        {data.payload?.totals && <div className="metrics">
            {Object.entries(data.payload.totals).map(([k, v]) => <section className="card metric" key={k}>
            <p>
            {t(({ delivered_amount: "Передано", paid_amount: "Поступления", return_credit_amount: "Возвраты", refund_amount: "Возвращено денег", net_amount: "Изменение баланса", turnover_amount: "Оборот", debt_amount: "Задолженность" } as any)[k] || k)}
            </p>
            <strong className={k === 'debt_amount' ? `debt-value${Number(v) > 0 ? ' positive' : ''}` : undefined}>
            {money(v)}
            </strong>
            </section>)}
        </div>}{group === 'weekly' ? <>
        <ErrorBox error={archive.error}/>
        <section className="card">
        <h2>{t("Сохранённые недельные отчёты")}</h2>
        {!archive.items.length && <p>{t("Архив пока пуст. Снимки формирует сервер по завершении недели.")}</p>}{archive.items.map(w => <details className="card" key={w.id}>
            <summary>{t("Неделя")}{' '}{new Date(w.start + 'T00:00:00+05:00').toLocaleDateString(locale(), { timeZone: 'Asia/Almaty' })} — {new Date(w.end_exclusive + 'T00:00:00+05:00').toLocaleDateString(locale(), { timeZone: 'Asia/Almaty' })}{' '}{t("· создан")}{' '}{new Date(w.created_at).toLocaleString(locale(), { timeZone: 'Asia/Almaty' })}
            </summary>
            <div className="metrics">
                {Object.entries(w.payload?.totals || {}).map(([k, v]) => <div key={k}>
                <p>
                {t(({ turnover_amount: 'Оборот', paid_amount: 'Поступления', debt_amount: 'Задолженность', net_amount: 'Изменение баланса' } as any)[k] || k)}
                </p>
                <strong className={k === 'debt_amount' ? `debt-value${Number(v) > 0 ? ' positive' : ''}` : undefined}>
                {money(v)}
                </strong>
                </div>)}
            </div>
            <button onClick={()=>downloadArchive(w)}>{t("Скачать сохранённый CSV")}</button><Records items={w.payload?.items || []} title={t("Операции сохранённого снимка")}/>
            </details>)}
        </section>
        </> : <Records items={data.items} title={t("Операции за период")}/>}
    </>;
}
export function Notifications() {
 const op=useOperations(),[tick,setTick]=useState(0),data=useCollection('/notifications?limit=20',op.revision+tick);
 useEffect(()=>{const timer=setInterval(()=>{if(document.visibilityState!=='hidden')setTick(n=>n+1)},10000);return()=>clearInterval(timer)},[]);
 return <><ErrorBox error={data.error||op.error}/><section className="card"><h2>{t('Уведомления')}</h2>{!data.loading&&!data.items.length&&<p>{t('Пока нет новых событий.')}</p>}{data.items.map(item=><article className="order-row" key={item.id}><span><NotificationMessage item={item}/><small>{new Date(item.created_at).toLocaleString(locale(),{timeZone:'Asia/Almaty'})}</small></span>{!item.read&&!item.read_at&&<button disabled={op.busy} onClick={()=>op.act('/notifications/'+item.id+'/read',{}).catch(()=>{})}>{t('Прочитано')}</button>}</article>)}{data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}</section></>;
}
export function CustomerReturns() {
    const data = useCollection('/returns');
    return <>
    <ErrorBox error={data.error}/>
    <Records items={data.items} title={t("Заявки на возврат и обмен")}/>
        {data.items.filter(r => r.kind === "exchange" && r.status === "approved").map(r => <section className="card" key={r.id}>
        <h3>{t("Новая поставка по обмену №")}{r.id.slice(0, 8)}
        </h3>
        <p>{t("Выберите замену в каталоге. Новая цена и разница будут рассчитаны сервером.")}</p>
        <button className="primary" onClick={() => { sessionStorage.setItem("exchange_id", r.id); location.hash = "catalog"; }}>{t("Выбрать замену")}</button>
        </section>)}
    </>;
}
export function CustomerOrderActions({ order, onChanged,returnsOnly=false }: {
    order: any;
    onChanged: () => void;
    returnsOnly?:boolean;
}) {
    const op = useOperations(), [kind, setKind] = useState('return'), [photos, setPhotos] = useState<string[]>([]), [qty, setQty] = useState<Record<string, number>>({});
    async function act(path: string, body: any) { const r = await op.act(path, body); onChanged(); return r; }
    return <div className="order-actions">
    <ErrorBox error={op.error}/>
    {!returnsOnly&&order.status === 'submitted' && <button disabled={op.busy} onClick={() => act('/orders/' + order.id + '/transition', { status: 'cancelled', version: order.version, reason: 'Отмена клиентом' }).catch(() => { })}>{t("Отменить заказ")}</button>}{!returnsOnly&&order.proposed_delivery_at && <>
        <p>{t("Предложенная дата:")}{' '}{new Date(order.proposed_delivery_at).toLocaleString(locale(), { timeZone: 'Asia/Almaty' })}
        </p>
        <button disabled={op.busy} onClick={() => act('/orders/' + order.id + '/reschedule-confirm', { accept: true, version: order.version }).catch(() => { })}>{t("Подтвердить перенос")}</button><button disabled={op.busy} onClick={()=>act("/orders/"+order.id+"/reschedule-confirm",{accept:false,version:order.version}).catch(()=>{})}>{t("Отказаться от переноса")}</button>
        </>}{['delivered','partially_delivered'].includes(order.status) && <form onSubmit={async (e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                try {
                    await act('/returns', { order_id: order.id, kind, reason: f.get('reason'), photo_ids: photos, items: (order.items || []).filter((i: any) => qty[i.product_id] > 0).map((i: any) => ({ product_id: i.product_id, quantity: qty[i.product_id] })) });
                    setPhotos([]);
                }
                catch { }
            }}>
        <h3>{t("Возврат или обмен")}</h3>
        <label>{t("Тип обращения")}<select value={kind} onChange={e => setKind(e.target.value)}>
        <option value="return">{t("Возврат")}</option>
        <option value="exchange">{t("Обмен")}</option>
        </select>
        </label>
            {order.items?.map((i: any) => <label key={i.product_id}>
            {i.name}{t(": принято")}{' '}{i.delivered_quantity ?? i.quantity}<input type="number" min="0" max={i.delivered_quantity ?? i.quantity} value={qty[i.product_id] || ''} onChange={e => setQty({ ...qty, [i.product_id]: Number(e.target.value) })}/>
            </label>)}<label>{t("Причина")}<textarea name="reason" required/>
        </label>
        <PhotoUpload orderId={order.id} purpose={kind} onUploaded={id => setPhotos(p => [...p, id])} act={op.act} busy={op.busy}/>
        <button className="primary" disabled={op.busy || !photos.length || !Object.values(qty).some(x => x > 0)}>{t("Отправить заявку")}</button>
        </form>}
    </div>;
}
export function DeliveryPoints() {
    const op = useOperations(), data = useCollection('/delivery-points', op.revision);
    return <>
    <ErrorBox error={op.error || data.error}/>
    <FieldsForm title={t("Добавить точку доставки")} fields={[{ name: 'address', label: 'Адрес' }, { name: 'recipient', label: 'Получатель' }, { name: 'phone', label: 'Телефон', type: 'tel' }, { name: 'window_start', label: 'Доставка с', type: 'time', required: false }, { name: 'window_end', label: 'Доставка до', type: 'time', required: false }]} onSubmit={d => op.act('/delivery-points', { ...d, window_start: d.window_start || undefined, window_end: d.window_end || undefined })} busy={op.busy}/>
    <Records items={data.items} title={t("Адреса доставки")}/>
    </>;
}

function downloadArchive(week:any){const keys=['id','created_at','client_id','order_id','kind','amount'];const escape=(value:any)=>'"'+String(value??'').replace(/"/g,'""')+'"';const csv='\ufeff'+[keys.join(','),...(week.payload?.items||[]).map((row:any)=>keys.map(k=>escape(row[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='week-'+week.start+'.csv';a.click();URL.revokeObjectURL(url);}
