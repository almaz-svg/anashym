import { t, locale } from './preferences';
import React, { useEffect, useRef, useState } from 'react';
import { ErrorBox, money, orderFrequency, status, useCollection } from './workspace';

type CustomerProfileData = {
    profile: {
        name: string; contact_name: string; phone: string; category: string;
        category_other: string; description: string; approval_status: string;
        preferred_payment_mode: string; expected_order_quantity: number;
        expected_order_frequency: string; period_days: number; credit_limit_amount: string;
    };
    from: string; to: string; generated_at: string; currency: 'KZT';
    balance: { debt_amount: string; advance_amount: string; overdue_amount: string; unconfirmed_payment_amount: string;reserved_refund_amount?:string };
    period: { delivered_amount: string; return_credit_amount: string; turnover_amount: string; paid_amount: string; refund_amount: string; outstanding_amount: string };
};

const dateLabel = (date: string) => new Intl.DateTimeFormat(locale(), { timeZone: 'Asia/Almaty', day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(date + 'T00:00:00+05:00'));
const periodLabel = (data: Pick<CustomerProfileData, 'from' | 'to'>) => `${dateLabel(data.from)} — ${dateLabel(data.to)}`;

function FinancialCard({ title, amount, debt = false, children }: { title: string; amount: string; debt?: boolean; children?: React.ReactNode }) {
    return <article className="card financial-card" aria-label={title}>
        <p>{title}</p>
        <strong className={debt ? `debt-value${Number(amount) > 0 ? ' positive' : ''}` : undefined}>{money(amount)}</strong>
        {children && <small>{children}</small>}
    </article>;
}

function CurrentBalance({ data }: { data: CustomerProfileData }) {
    return <>
        <FinancialCard title={t("Общая задолженность")} amount={data.balance.debt_amount} debt>
            {Number(data.balance.overdue_amount) > 0 ? <>{t("Из неё просрочено:")}{' '}<span className="debt-value positive">{money(data.balance.overdue_amount)}</span></> : t('За все поставки на текущий момент')}
        </FinancialCard>
        <FinancialCard title={t("Аванс")} amount={data.balance.advance_amount}>{t("Доступен для следующих поставок")}</FinancialCard>
        <FinancialCard title={t("Ожидает подтверждения")} amount={data.balance.unconfirmed_payment_amount}>{t("Пока не уменьшает задолженность")}</FinancialCard>
        {Number(data.balance.reserved_refund_amount)>0&&<FinancialCard title={t('Ожидает возврата')} amount={data.balance.reserved_refund_amount!}>{t('Зарезервировано для возврата денег')}</FinancialCard>}
    </>;
}

export function PaymentFinancialSummary({ revision }: { revision: number }) {
    const [retry, setRetry] = useState(0);
    const data = useCollection('/profile', revision + retry);
    const summary = data.payload as CustomerProfileData | null;
    return <section aria-labelledby="payment-summary-title" className="period-summary">
        <div className="financial-summary-header">
            <div><h2 id="payment-summary-title">{t("Ваши расчёты")}</h2><p className="muted">{t("Текущий баланс и подтверждённые оплаты за неделю")}</p></div>
            <a href="#debt">{t("Подробнее о задолженности")}</a>
        </div>
        {data.loading ? <p role="status" className="card">{t("Загружаем денежную сводку…")}</p> : data.error ? <div className="card">
            <ErrorBox error={data.error}/><button type="button" onClick={() => setRetry(r => r + 1)}>{t("Повторить загрузку сводки")}</button>
        </div> : summary && <>
            <div className="financial-summary">
                <CurrentBalance data={summary}/>
                <FinancialCard title={t("Подтверждённые оплаты за неделю")} amount={summary.period.paid_amount}>{periodLabel(summary)}</FinancialCard>
            </div>
            <p className="financial-summary-note">{t("В задолженности учтены подтверждённые оплаты и зачтённые возвраты.")}</p>
        </>}
    </section>;
}

function currentWeek() {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Almaty', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
    const part = (type: string) => parts.find(item => item.type === type)!.value;
    const start = new Date(`${part('year')}-${part('month')}-${part('day')}T00:00:00Z`);
    start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + 6);
    return { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) };
}

export function CustomerProfile() {
    const [dates, setDates] = useState(currentWeek);
    const datesEdited = useRef(false);
    const [query, setQuery] = useState('');
    const [revision, setRevision] = useState(0);
    const [identity, setIdentity] = useState<CustomerProfileData['profile'] | null>(null);
    const data = useCollection('/profile' + query, revision);
    const summary = data.payload as CustomerProfileData | null;
    const profile = summary?.profile || identity;
    const invalidDates = !dates.from || !dates.to || dates.from > dates.to;

    useEffect(() => {
        if (summary) {
            setIdentity(summary.profile);
            if (!datesEdited.current) setDates({ from: summary.from, to: summary.to });
        }
    }, [summary]);

    return <>
        <section className="card" aria-labelledby="customer-profile-title">
            <div className="profile-heading">
                <div><p className="eyebrow">{t("Аккаунт заказчика")}</p><h2 id="customer-profile-title">{profile?.name || t('Данные заказчика')}</h2>{profile && <p className="muted">{status(profile.category)}{profile.category_other ? ` · ${profile.category_other}` : ''} · {status(profile.approval_status)}</p>}</div>
            </div>
            {profile && <>
                <dl className="profile-details">
                    <div><dt>{t("Контактное лицо")}</dt><dd>{profile.contact_name || t('Не указано')}</dd></div>
                    <div><dt>{t("Телефон")}</dt><dd>{profile.phone || t('Не указан')}</dd></div>
                    <div><dt>{t("Способ оплаты")}</dt><dd>{status(profile.preferred_payment_mode)}</dd></div>
                    <div><dt>{t("Период отсрочки")}</dt><dd>{t('{{count}} дней', { count: profile.period_days })}</dd></div>
                    <div><dt>{t("Лимит отсрочки")}</dt><dd>{money(profile.credit_limit_amount)}</dd></div>
                    <div><dt>{t("Порций за заказ")}</dt><dd>{profile.expected_order_quantity || t('Не указано')}</dd></div>
                    <div><dt>{t("Частота заказов")}</dt><dd>{orderFrequency(profile.expected_order_frequency)}</dd></div>
                </dl>
                {profile.description && <p className="muted">{profile.description}</p>}
            </>}
        </section>

        <section className="card" aria-labelledby="account-period-title">
            <h2 id="account-period-title">{t("Расчёты за период")}</h2>
            <p className="muted" id="account-period-help">{t("Выберите даты поставок, чтобы увидеть суммы и остаток к оплате.")}</p>
            <form className="account-period-form" aria-describedby="account-period-help" onSubmit={event => {
                event.preventDefault();
                if (invalidDates) return;
                datesEdited.current = false;
                setQuery(`?from=${encodeURIComponent(dates.from)}&to=${encodeURIComponent(dates.to)}`);
                setRevision(r => r + 1);
            }}>
                <label>{t("Начало периода")}<input type="date" required value={dates.from} disabled={data.loading} onChange={event => { const from = event.target.value; datesEdited.current = true; setDates(value => ({ ...value, from })); }}/></label>
                <label>{t("Конец периода")}<input type="date" required min={dates.from} value={dates.to} disabled={data.loading} onChange={event => { const to = event.target.value; datesEdited.current = true; setDates(value => ({ ...value, to })); }}/></label>
                <div className="account-period-actions">
                    <button className="primary" disabled={data.loading || invalidDates}>{t("Показать период")}</button>
                    <button type="button" disabled={data.loading} onClick={() => { datesEdited.current = false; setDates(currentWeek()); setQuery(''); setRevision(r => r + 1); }}>{t("Текущая неделя")}</button>
                </div>
            </form>
            {dates.from && dates.to && dates.from > dates.to && <p className="error" role="alert">{t("Конец периода должен быть не раньше начала.")}</p>}
        </section>

        {data.loading ? <p className="card" role="status">{t("Загружаем профиль и расчёты…")}</p> : data.error ? <div className="card">
            <ErrorBox error={data.error}/><button type="button" onClick={() => setRevision(r => r + 1)}>{t("Повторить загрузку профиля")}</button>
        </div> : summary && <>
            <section className="period-summary" aria-labelledby="account-balance-title">
                <div className="financial-summary-header"><div><h2 id="account-balance-title">{t("Текущий баланс")}</h2><p className="muted">{t("По всем поставкам, независимо от выбранного периода")}</p></div><a href="#debt">{t("Подробнее о задолженности")}</a></div>
                <div className="financial-summary"><CurrentBalance data={summary}/></div>
            </section>
            <section className="period-summary" aria-labelledby="selected-period-title">
                <div className="financial-summary-header"><div><h2 id="selected-period-title">{t("Выбранный период")}</h2><p className="muted">{periodLabel(summary)}</p></div></div>
                <div className="financial-summary">
                    <FinancialCard title={t("Передано за период")} amount={summary.period.delivered_amount}>{t("Стоимость фактически переданных товаров")}</FinancialCard>
                    <FinancialCard title={t("Подтверждённые оплаты")} amount={summary.period.paid_amount}>{t("По дате подтверждения оплаты")}</FinancialCard>
                    <FinancialCard title={t("Осталось оплатить по поставкам периода")} amount={summary.period.outstanding_amount} debt>{t("С учётом оплат и зачтённых возвратов")}</FinancialCard>
                </div>
                <p className="financial-summary-note">{t("Остаток относится только к поставкам выбранного периода. Учтены подтверждённые оплаты и возвраты, в том числе после его окончания.")}</p>
                {(Number(summary.period.return_credit_amount) > 0 || Number(summary.period.refund_amount) > 0) && <p className="financial-summary-note">{t("Зачтено возвратов за период:")}{' '}{money(summary.period.return_credit_amount)}{t(". Возвращено денег:")}{' '}{money(summary.period.refund_amount)}.</p>}
            </section>
            <div className="profile-actions"><a href="#payments" className="primary">{t("Перейти к оплатам")}</a></div>
        </>}
    </>;
}
