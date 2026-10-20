import {t,locale} from './preferences';
import {money,status} from './workspace';

export function OrderSummary({order:o}:{order:any}) {
    const delivered=o.status==='delivered'||Number(o.delivered_total_amount)>0;
    const address=typeof o.address_snapshot==='object'?o.address_snapshot?.address:'';
    return <dl className="order-summary">
        {o.client_name&&<div><dt>{t('Клиент')}</dt><dd>{o.client_name}</dd></div>}
        {address&&<div><dt>{t('Адрес доставки')}</dt><dd>{address}</dd></div>}
        <div><dt>{t('Доставка')}</dt><dd>{new Date(o.requested_delivery_at).toLocaleString(locale(),{timeZone:'Asia/Almaty'})}</dd></div>
        <div><dt>{t('Курьер')}</dt><dd>{o.courier_name||t('Ещё не назначен')}</dd></div>
        <div><dt>{t('Способ расчёта')}</dt><dd>{t(o.payment_mode==='cash'?'При получении':o.payment_mode==='kaspi'?'Предоплата Kaspi':'Отсрочка')}</dd></div>
        <div><dt>{t('Состояние оплаты')}</dt><dd>{status(o.payment_status||'unpaid')}</dd></div>
        {Number(o.cash_paid_amount)>0&&<div><dt>{t('Оплачено наличными')}</dt><dd>{money(o.cash_paid_amount)}</dd></div>}
        {Number(o.kaspi_paid_amount)>0&&<div><dt>{t('Оплачено Kaspi')}</dt><dd>{money(o.kaspi_paid_amount)}</dd></div>}
        {delivered&&<div><dt>{t('Осталось оплатить')}</dt><dd className={Number(o.outstanding_amount)>0?'debt-value positive':undefined}>{money(o.outstanding_amount||'0')}</dd></div>}
    </dl>;
}

/** Visible directly in the queue, without opening another view. */
export function OrderRowSummary({order:o}:{order:any}) {
    const address=typeof o.address_snapshot==='object'?o.address_snapshot?.address:'';
    return <>
        <small>{o.items?.map((item:any)=>`${item.name} × ${item.quantity}`).join(' · ')}</small>
        {address&&<small>{address}</small>}
        <small>{status(o.payment_mode)} · {status(o.payment_status||'unpaid')}{o.courier_name&&` · ${t('Курьер')}: ${o.courier_name}`}</small>
        {(Number(o.cash_paid_amount)>0||Number(o.kaspi_paid_amount)>0)&&<small>{Number(o.cash_paid_amount)>0&&`${t('Наличные')}: ${money(o.cash_paid_amount)}`}{Number(o.cash_paid_amount)>0&&Number(o.kaspi_paid_amount)>0?' · ':''}{Number(o.kaspi_paid_amount)>0&&`Kaspi: ${money(o.kaspi_paid_amount)}`}</small>}
        {Number(o.outstanding_amount)>0&&<small className="debt-value positive">{t('Осталось оплатить')}: {money(o.outstanding_amount)}</small>}
    </>;
}
