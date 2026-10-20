import React from 'react';
import { LogOut, Mail } from 'lucide-react';
import { BrandLogo } from './brand-logo';
import { PreferencesControls, t } from './preferences';
import { NotificationBell } from './account-features';
import { DebtIndicator } from './debt-indicator';

export function AccountHeader({ user, logout, busy = false, staffRole, onNotifications, onDebt }: {
    user: any; logout: () => void; busy?: boolean; staffRole?: string; onNotifications?:()=>void; onDebt?:()=>void;
}) {
    const identity = <>
        <span className="avatar" aria-hidden="true">{(user.client_name || user.name || user.phone || '?')[0]}</span>
        <span><strong>{user.client_name || user.name || user.phone}</strong><small>{staffRole ? t(staffRole) : t('Кабинет заказчика')}</small></span>
    </>;
    return <><header className="account-header">
        {staffRole ? <div className="account-identity">{identity}</div> : <a className="account-identity" href="#profile" title={t('Мой профиль')} aria-label={t('Мой профиль')}>{identity}</a>}
        <div className="account-controls">
            {!user.must_change_password && <NotificationBell onOpen={onNotifications}/>}
            <PreferencesControls />
            <div className="account-actions">
                <button type="button" className="account-logout" onClick={logout} disabled={busy}><LogOut size={16} aria-hidden="true"/>{t('Выйти')}</button>
            </div>
        </div>
    </header><DebtIndicator user={user} onOpen={onDebt}/></>;
}

export function SiteFooter({ customer = false }: { customer?: boolean }) {
    return <footer className="site-footer" aria-label={t('О кондитерской')}>
        <div className="footer-grid">
            <section>
                <div className="brand"><BrandLogo/></div>
                <h2>{t('О нас')}</h2>
                <p>{t('Готовим десерты для постоянных покупателей: кофеен, магазинов, ресторанов, компаний и частных клиентов.')}</p>
                <p>{t('В личном кабинете можно планировать поставки, оформлять заказы и следить за оплатами.')}</p>
            </section>
            <section>
                <h2>{t('Связаться с нами')}</h2>
                <a className="footer-contact" href="mailto:almazzmusulamnkull@gmail.com"><Mail size={18} aria-hidden="true"/><span>almazzmusulamnkull@gmail.com</span></a>
                <p>{t('Напишите нам по вопросам сотрудничества, заказов и расчётов.')}</p>
            </section>
            {customer && <section>
                <h2>{t('Ваш кабинет')}</h2>
                <nav aria-label={t('Навигация в подвале')}>
                    <a href="#profile">{t('Мой профиль')}</a><a href="#orders">{t('Заказы')}</a>
                    <a href="#payments">{t('Оплаты')}</a><a href="#debt">{t('Задолженность')}</a>
                </nav>
            </section>}
        </div>
        <div className="footer-bottom"><span>© {new Date().getFullYear()} {t('Кондитерская')}</span><span>{t('Расчёты в KZT · Время Алматы (UTC+5)')}</span></div>
    </footer>;
}
