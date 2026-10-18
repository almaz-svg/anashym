/// <reference types="vite/client" />
import React, { useEffect, useState, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { CakeSlice, ShoppingBasket, ClipboardList, Wallet, ChartNoAxesCombined, UserRound, ArrowRight, Leaf, RefreshCw } from 'lucide-react';
import '@fontsource/manrope/cyrillic-400.css';
import '@fontsource/manrope/cyrillic-600.css';
import '@fontsource/manrope/cyrillic-700.css';
import '@fontsource/manrope/cyrillic-ext-400.css';
import '@fontsource/manrope/cyrillic-ext-600.css';
import '@fontsource/manrope/cyrillic-ext-700.css';
import '@fontsource/manrope/latin-400.css';
import '@fontsource/manrope/latin-600.css';
import '@fontsource/manrope/latin-700.css';
import { apiRequest, ApiError, isDefinitiveFailure } from './api';
import './style.css';
import { Payments, Reports, Notifications, CustomerOrderActions, CustomerReturns, DeliveryPoints, RefundObligations } from './customer';
import { status } from './workspace';
import { StaffWorkspace } from './staff';
import { CustomerProfile } from './customer-profile';
import { AccountHeader, SiteFooter } from './account-shell';
import { PreferencesControls, usePreferences, t, locale } from './preferences';
import { OrderEvidence, PasswordChange } from './account-features';
import { reconcileCart } from './cart';
type Product = {
    id: string;
    name: string;
    price_amount: string;
    available_qty: number;
    preorder_available_qty: number;
    preparation_minutes: number;
    image_url?: string;
    description?: string;
    shelf_life_hours?: number;
    available_dates?: string[];
};
const money = (value: string) => new Intl.NumberFormat(locale(), { style: 'currency', currency: 'KZT', maximumFractionDigits: 2 }).format(Number(value));
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Almaty', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
function ErrorMessage({ error }: {
    error: unknown;
}) {
    return error ? <div role="alert" className="error">
    <strong>
    {error instanceof Error ? t(error.message) : t("Не удалось загрузить данные")}
    </strong>
        {error instanceof ApiError && Object.entries(error.field_errors).map(([k, v]) => <p key={k}>
        {({ phone: t("Телефон"), password: t("Пароль"), name: t("Название"), category: t("Категория"), description: t("Описание"), expected_order_quantity: t("Количество"), expected_order_frequency: t("Частота заказов"), items: t("Позиции заказа"), requested_delivery_at: t("Время доставки"), delivery_point_id: t("Точка доставки") } as Record<string, string>)[k] || k}: {v.map(message => t(message)).join(' ')}
        </p>)}{error instanceof ApiError && <small>{t("Код:")}{" "}{error.code}
        </small>}
    </div> : null;
}
function App() {
    usePreferences();
    const [user, setUser] = useState<any>(undefined), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [activate, setActivate] = useState(false), [register, setRegister] = useState(false), [category, setCategory] = useState('');
    const [page, setPage] = useState(location.hash.slice(1) || 'catalog'), [date, setDate] = useState(today()), [products, setProducts] = useState<Product[]>([]), [points, setPoints] = useState<any[]>([]), [balance, setBalance] = useState<any>(null), [orders, setOrders] = useState<any[]>([]), [detail, setDetail] = useState<any>(null), [qty, setQty] = useState<Record<string, number>>({}), [point, setPoint] = useState(''), [time, setTime] = useState('12:00'), [paymentMode, setPaymentMode] = useState('deferred'), [loading, setLoading] = useState(false), [cursor, setCursor] = useState<string | null>(null),[orderCursor,setOrderCursor]=useState<string|null>(null);
    const catalogCache = useRef<Record<string, Product>>({});
    const [priceReview,setPriceReview]=useState(false),[priceAccepted,setPriceAccepted]=useState(false);
    const loadVersion = useRef(0);
    const attempt = useRef<{
        body: string;
        key: string;
    } | null>(null);
    useEffect(() => { const h = () => setPage(location.hash.slice(1) || 'catalog'); window.addEventListener('hashchange', h); return () => window.removeEventListener('hashchange', h); }, []);
    useEffect(() => { window.scrollTo(0, 0); }, [user?.id, user?.phone, page]);
    async function session() {
        setError(null);
        try {
            await apiRequest('/auth/csrf');
            setUser(await apiRequest('/auth/me'));
        }
        catch (e) {
            if (e instanceof ApiError && e.status === 401)
                setUser(null);
            else {
                setError(e);
                setUser(null);
            }
        }
    }
    useEffect(() => { session(); }, []);
    async function load(append = false) {
        const version = ++loadVersion.current;
        setLoading(true);
        setError(null);
        try {
            if (page === 'catalog') {
                const [catalog, p, b] = await Promise.all([apiRequest('/catalog?delivery_date=' + date + '&limit=20' + (append && cursor ? '&cursor=' + encodeURIComponent(cursor) : '')), apiRequest('/delivery-points'), apiRequest('/balance')]);
                if (version !== loadVersion.current)
                    return;
                catalog.items.forEach((p: Product) => { catalogCache.current[p.id] = p; });
                setProducts(old => append ? [...old, ...catalog.items] : catalog.items);
                setCursor(catalog.next_cursor);
                setPoints(p.items);
                setPoint(old => old || p.items[0]?.id || '');
                setBalance(b);
            }
            if (page === 'debt') {
                const result = await apiRequest('/balance');
                if (version === loadVersion.current)
                    setBalance(result);
            }
            if (page === 'orders') {
                const result = await apiRequest('/orders?limit=20'+(append&&orderCursor?'&cursor='+encodeURIComponent(orderCursor):''));
                if (version === loadVersion.current){setOrders(old=>append?[...old,...result.items.filter((x:any)=>!old.some(y=>y.id===x.id))]:result.items);setOrderCursor(result.next_cursor||null);}
            }
        }
        catch (e) {
            if (version === loadVersion.current)
                setError(e);
        }
        finally {
            if (version === loadVersion.current)
                setLoading(false);
        }
    }
    useEffect(() => {
        if (user && !user.must_change_password && (!user.role || user.role === 'customer') && ['active', 'approved'].includes(user.approval_status))
            load();
    }, [user, page, date]);
    async function loadDetail(id: string) {
        const version = loadVersion.current;
        try {
            const result = await apiRequest('/orders/' + id);
            if (version !== loadVersion.current) return;
            setDetail(result);
            setError(null);
        } catch (e) {
            if (version === loadVersion.current) setError(e);
        }
    }
    async function auth(e: React.FormEvent<HTMLFormElement>) {
        e.preventDefault();
        setBusy(true);
        setError(null);
        const f = new FormData(e.currentTarget);
        const body: any = { phone: f.get('phone'), password: f.get('password') };
        if (activate) {
            try {
                await apiRequest('/auth/csrf');
                await apiRequest('/auth/accept-invitation', { method: 'POST', body: JSON.stringify({ token: f.get('token'), password: body.password }) });
                setActivate(false);
                setRegister(false);
            }
            catch (e) {
                setError(e);
            }
            finally {
                setBusy(false);
            }
            return;
        }
        if (register)
            Object.assign(body, { name: f.get('name'), category, category_other: f.get('category_other') || '', description: f.get('description'), expected_order_quantity: Number(f.get('expected_order_quantity')), expected_order_frequency: f.get('expected_order_frequency'), preferred_payment_mode: f.get('preferred_payment_mode'), requested_period_days: Number(f.get('requested_period_days')) });
        try {
            await apiRequest('/auth/csrf');
            const u = await apiRequest('/auth/' + (register ? 'register' : 'login'), { method: 'POST', body: JSON.stringify(body) });
            if (register) {
                await apiRequest('/auth/login', { method: 'POST', body: JSON.stringify({ phone: body.phone, password: body.password }) });
            }
            setUser(u);
        }
        catch (e) {
            setError(e);
        }
        finally {
            setBusy(false);
        }
    }
    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if(priceReview&&!priceAccepted)return;
        setBusy(true);
        setError(null);
        const body = JSON.stringify({ kind: date === today() ? 'regular' : 'preorder', delivery_point_id: point, requested_delivery_at: date + 'T' + time + ':00+05:00', payment_mode: paymentMode, exchange_id: sessionStorage.getItem('exchange_id') || undefined, items: Object.values(catalogCache.current).filter(p => qty[p.id] > 0).map(p => ({ product_id: p.id, quantity: qty[p.id], expected_unit_price: p.price_amount })) });
        if (!attempt.current || attempt.current.body !== body)
            attempt.current = { body, key: crypto.randomUUID() };
        try {
            const order = await apiRequest('/orders', { method: 'POST', body, headers: { 'Idempotency-Key': attempt.current.key } });
            setDetail(order);
            setQty({});
            attempt.current = null;
            sessionStorage.removeItem('exchange_id');
            setPriceReview(false);setPriceAccepted(false);
            location.hash = 'orders';
        }
        catch (e) {
            setError(e);
            if(e instanceof ApiError&&e.code==='PRICE_CHANGED'){
                setPriceReview(true);setPriceAccepted(false);
                try{
                    const current:Product[]=[];let next:string|null=null;
                    do{const catalogPage:{items:Product[];next_cursor:string|null}=await apiRequest('/catalog?delivery_date='+date+'&limit=100'+(next?'&cursor='+encodeURIComponent(next):''));current.push(...catalogPage.items);next=catalogPage.next_cursor||null}while(next);
                    catalogCache.current=Object.fromEntries(current.map(product=>[product.id,product]));
                    setProducts(current);setCursor(null);setQty(reconcileCart(current,qty,date!==today()).quantities);
                }catch(refreshError){setError(refreshError)}
            }
            if (isDefinitiveFailure(e))
                attempt.current = null;
        }
        finally {
            setBusy(false);
        }
    }
    async function logout() {
        setBusy(true);
        try {
            await apiRequest('/auth/logout', { method: 'POST' });
            sessionStorage.removeItem('exchange_id');
            ++loadVersion.current;
            catalogCache.current = {};
            attempt.current = null;
            setUser(null);
            setDetail(null);
            setQty({});
            setBalance(null);
            setOrders([]);
            setProducts([]);
            setPoints([]);
            setPoint('');
            setCursor(null);setOrderCursor(null);
            setError(null);
            setLoading(false);
        }
        catch (e) {
            setError(e);
        }
        finally {
            setBusy(false);
        }
    }
    if(user?.must_change_password)return <PasswordChange onChanged={session} logout={logout}/>;
    if (user && user.role && user.role !== 'customer')
        return <StaffWorkspace user={user} logout={logout} busy={busy} sessionError={error}/>;
    const nav = [['profile', t("Мой профиль"), UserRound], ['catalog', t("Каталог"), ShoppingBasket], ['orders', t("Заказы"), ClipboardList], ['payments', t("Оплаты"), Wallet], ['debt', t("Задолженность"), ChartNoAxesCombined], ['reports', t("Отчёты"), ClipboardList], ['notifications', t("Уведомления"), ClipboardList], ['points', t("Адреса доставки"), ClipboardList]] as const;
    if (user === undefined)
        return <main className="initial" role="status">{t("Подключаемся к кондитерской…")}</main>;
    if (!user)
        return <div className="auth-page"><div className="auth-preferences"><PreferencesControls /></div><main className="auth">
        <section className="intro">
        <span className="brand">
        <CakeSlice />{t("Кондитерская")}</span>
        <div>
        <span className="eyebrow">{t("КАБИНЕТ ПАРТНЁРА")}</span>
        <h1>{t("Свежие десерты.")}<br />{t("Простые заказы.")}</h1>
        <p>{t("Планируйте поставки, заказывайте продукцию и следите за взаиморасчётами в одном месте.")}</p>
        </div>
        <div className="intro-note">
        <Leaf />{t("От заказа до расчёта — всё под рукой.")}</div>
        </section>
        <section className="auth-form">
        <div className="tabs">
        <button className={!register && !activate ? 'selected' : ''} onClick={() => { setActivate(false); setRegister(false); setError(null); }}>{t("Вход")}</button>
        <button className={register ? 'selected' : ''} onClick={() => { setActivate(false); setRegister(true); setError(null); }}>{t("Регистрация")}</button>
        </div>
        <h2>
        {activate ? t('Приглашение') : register ? t("Давайте познакомимся") : t("Рады вас видеть")}
        </h2>
        <p>
        {activate ? t('Введите код приглашения и установите пароль.') : register ? t("Расскажите о себе. Администратор проверит заявку и откроет доступ.") : t("Войдите, чтобы оформить следующую поставку.")}
        </p>
        <ErrorMessage error={error}/>
        <form key={activate ? 'invitation' : register ? 'register' : 'login'} onSubmit={auth}>
            {activate ? <label>{t("Код приглашения")}<input name="token" required/>
            </label> : <label>{t(register ? "Телефон" : "Логин или телефон")}<input name="phone" type={register ? 'tel' : 'text'} autoComplete={register ? 'tel' : 'username'} placeholder={register ? '+77001234567' : undefined} pattern={register ? '\\+[1-9][0-9]{7,14}' : undefined} required/>
            </label>}<label>{t("Пароль")}<input name="password" type="password" minLength={activate ? 12 : register ? 8 : 1} autoComplete={register || activate ? 'new-password' : 'current-password'} required/>
        </label>
            {register && <>
            <label>{t("Название или имя")}<input name="name" autoComplete="organization" required/>
            </label>
            <label>{t("Категория")}<select required value={category} onChange={e => setCategory(e.target.value)}>
            <option value="">{t("Выберите категорию")}</option>
            <option value="coffee_shop">{t("Кофейня")}</option>
            <option value="store">{t("Магазин")}</option>
            <option value="restaurant">{t("Ресторан / кафе")}</option>
            <option value="company">{t("Компания")}</option>
            <option value="individual">{t("Частный покупатель")}</option>
            <option value="other">{t("Другое")}</option>
            </select>
            </label>
                {category === 'other' && <label>{t("Уточните категорию")}<input name="category_other" required/>
                </label>}<label>{t("Описание деятельности")}<textarea name="description" required rows={2}/>
            </label>
            <div className="form-row">
            <label>{t("Порций за заказ")}<input type="number" name="expected_order_quantity" min="1" required/>
            </label>
            <label>{t("Как часто")}<select name="expected_order_frequency">
            <option value="Ежедневно">{t("Ежедневно")}</option>
            <option value="Несколько раз в неделю">{t("Несколько раз в неделю")}</option>
            <option value="Раз в неделю">{t("Раз в неделю")}</option>
            <option value="По необходимости">{t("По необходимости")}</option>
            </select>
            </label>
            </div>
            <div className="form-row">
            <label>{t("Предпочтительный способ оплаты")}<select name="preferred_payment_mode">
            <option value="deferred">{t("Отсрочка")}</option>
            <option value="kaspi">Kaspi</option>
            <option value="cash">{t("Наличные")}</option>
            </select>
            </label>
            <label>{t("Желаемый период отсрочки")}<select name="requested_period_days">
            <option value="7">{t("7 дней")}</option>
            <option value="14">{t("14 дней")}</option>
            <option value="30">{t("30 дней")}</option>
            </select>
            </label>
            </div>
            </>}<button className="primary" disabled={busy}>
        {busy ? t("Отправляем…") : activate ? t("Установить пароль") : register ? t("Отправить заявку") : t("Войти")}<ArrowRight size={18}/>
        </button>
        </form>
        <button type="button" className="invitation-link" onClick={() => { setActivate(!activate); setRegister(false); setError(null); }}>{activate ? t('Вернуться ко входу') : t('У меня есть приглашение')}</button>
        <small>{t("Защищённый кабинет. Доступ к заказам открывается после одобрения.")}</small>
        </section>
        </main><div className="public-footer"><SiteFooter /></div></div>;
    return <div className="shell">
    <aside>
    <a className="brand" href="#catalog">
    <CakeSlice />{t("Кондитерская")}</a>
    <span className="eyebrow">{t("ЛИЧНЫЙ КАБИНЕТ")}</span>
    <nav aria-label={t("Основная навигация")}>
        {nav.map(([id, title, Icon]) => <a href={'#' + id} key={id} className={page === id ? 'active' : ''} aria-current={page === id ? 'page' : undefined}>
        <Icon size={20}/>
        {title}
        </a>)}
    </nav>
    <div className="sidebar-note">
    <Leaf />
    <strong>{t("Всегда на связи")}</strong>
    <p>{t("По вопросам поставки обращайтесь к вашему менеджеру.")}</p>
    </div>
    </aside>
    <main className="content">
    <AccountHeader user={user} logout={logout} busy={busy}/>
    <ErrorMessage error={error}/>
        {['pending', 'rejected'].includes(user.approval_status) && page !== 'profile' ? <section className="card pending">
        <span className="badge">
        {user.approval_status === "rejected" ? t("Заявка отклонена") : t("Заявка на рассмотрении")}
        </span>
        <h1>{t("Спасибо за знакомство!")}</h1>
        <p>
        {user.approval_status === "rejected" ? t("Обратитесь к администратору, чтобы уточнить условия доступа.") : t("Администратор проверяет вашу заявку. Каталог и заказы станут доступны после одобрения.")}
        </p>
        <button onClick={session}>
        <RefreshCw size={16}/>{t("Проверить статус")}</button>
        </section> : <>
        <div className="page-title">
        <div>
        <span className="eyebrow">{t("ВАША КОНДИТЕРСКАЯ, БЛИЖЕ")}</span>
        <h1>
        {nav.find(x => x[0] === page)?.[1] || t("Кабинет")}
        </h1>
        <p>
        {page === 'catalog' ? t("Выберите десерты для следующей поставки.") : page === 'debt' ? t("Подтверждённые суммы и доступная отсрочка.") : t("Вся информация о ваших операциях.")}
        </p>
        </div>
            {['catalog', 'orders', 'debt'].includes(page) && <button onClick={() => load()} disabled={loading}>
            <RefreshCw size={16}/>{t("Обновить")}</button>}
        </div>
        {loading && <div role="status" className="loading">{t("Загружаем актуальные данные…")}</div>}
 {page === 'catalog' && <>
            <section className="welcome">
            <div>
            <span className="badge">{t("Отсрочка оплаты")}</span>
            <h2>{t("Поставка начинается здесь")}</h2>
            <p>{t("Выберите дату и количество. Стоимость и резерв подтвердит сервер при оформлении.")}</p>
            </div>
            <div className="welcome-stat">
            <small>{t("Доступно по лимиту")}</small>
            <strong>
            {balance ? money(balance.available_credit_amount) : '—'}
            </strong>
            <small>{t("Резерв ещё не является долгом")}</small>
            </div>
            </section>
            <form onSubmit={submit}>
            <div className="toolbar">
            <label>{t("Дата поставки")}<input type="date" min={today()} value={date} onChange={e => { setDate(e.target.value); setQty({});catalogCache.current={};setPriceReview(false);setPriceAccepted(false); }} required/>
            </label>
            <span className="muted">
            {date === today() ? t("Готовая продукция") : t("Предзаказ на выбранную дату")}
            </span>
            </div>
            <div className="products">
                {products.map(p => <article className="card product" key={p.id}>
                <div className="product-image">
                    {p.image_url ? <img src={p.image_url} alt={p.name} width="400" height="220"/> : <>
                    <CakeSlice size={36}/>
                    <span>{t("Фото пока нет")}</span>
                    </>}
                </div>
                <div className="product-body">
                <h3>
                {p.name}
                </h3>
                {p.description&&<p>{p.description}</p>}
                {p.shelf_life_hours!=null&&<p>{t('Срок хранения, часов')}: {p.shelf_life_hours}</p>}
                {!!p.available_dates?.length&&<p className="muted">{t('Доступные даты')}: {p.available_dates.join(', ')}</p>}
                <p>
                {t('Доступно порций: {{count}} · {{minutes}} мин', {count: date === today() ? p.available_qty : p.preorder_available_qty, minutes: p.preparation_minutes})}</p>
                <div className="product-bottom">
                <strong>
                {money(p.price_amount)}<small>{t("/ порция")}</small>
                </strong>
                <label className="quantity">
                <span className="sr-only">{t("Количество:")}{" "}{p.name}
                </span>
                <input type="number" inputMode="numeric" min="0" max={date === today() ? p.available_qty : p.preorder_available_qty} placeholder="0" value={qty[p.id] || ''} onChange={e => { const raw = e.currentTarget.value; const quantity = Math.max(0, Number(raw)); e.currentTarget.value = raw === '' ? '' : String(quantity); setQty({ ...qty, [p.id]: quantity });setPriceAccepted(false); }}/>
                </label>
                </div>
                </div>
                </article>)}
            </div>
                {!loading && !products.length && <section className="card empty">
                <CakeSlice />
                <h2>{t("На эту дату пока нет продукции")}</h2>
                <p>{t("Выберите другую дату или обновите каталог.")}</p>
                </section>}{cursor && <button type="button" onClick={() => load(true)} disabled={loading}>{t("Показать ещё")}</button>}<section className="card checkout">
                {sessionStorage.getItem("exchange_id") && <p className="notice">{t("Оформляется новая поставка по одобренному обмену.")}{" "}<button type="button" onClick={() => { sessionStorage.removeItem("exchange_id"); setQty({ ...qty }); }}>{t("Обычный заказ")}</button>
                </p>}<div>
            <h2>{t("Оформление поставки")}</h2>
            <p>{t('Выбрано позиций: {{count}}. Итоговую сумму рассчитаем при оформлении.', {count: Object.values(qty).filter(x => x > 0).length})}</p>
            </div>
            <div className="form-row">
            <label>{t("Точка доставки")}<select required value={point} onChange={e => setPoint(e.target.value)}>
            <option value="">{t("Выберите точку")}</option>
                {points.map(p => <option key={p.id} value={p.id}>
                {p.address}
                </option>)}
            </select>
            </label>
            <label>{t("Время доставки")}<input type="time" required value={time} onChange={e => setTime(e.target.value)}/>
            </label>
            </div>
            {!points.length && <p className="muted">{t("Нет доступных точек доставки. Обратитесь к администратору.")}</p>}<label>{t("Способ оплаты")}<select value={paymentMode} onChange={e => setPaymentMode(e.target.value)}>
            <option value="deferred">{t("Отсрочка (при одобренном лимите)")}</option>
            <option value="kaspi">{t("Предоплата Kaspi")}</option>
            <option value="cash">{t("Наличные при получении")}</option>
            </select>
            </label>
            <p className="muted">{t("Kaspi проверяет кассир. Наличные — полный расчёт за принятое количество.")}</p>
            {priceReview&&<div className="notice" role="alert"><strong>{t('Цены изменились. Каталог и корзина обновлены.')}</strong><p>{t('Проверьте количество и новую сумму перед повторной отправкой. Недоступные позиции удалены.')}</p><p>{t('Новая сумма')}: <strong>{money(String(reconcileCart(Object.values(catalogCache.current),qty,date!==today()).total))}</strong></p><label className="checkbox-label"><input type="checkbox" checked={priceAccepted} onChange={e=>setPriceAccepted(e.target.checked)}/>{t('Подтверждаю новую сумму заказа')}</label></div>}
            <button className="primary" disabled={busy || !point || !Object.values(qty).some(x => x > 0)||(priceReview&&!priceAccepted)}>
            {busy ? t("Оформляем…") : attempt.current ? t("Повторить отправку с прежним ключом") : t("Оформить заказ")}<ArrowRight size={18}/>
            </button>
            </section>
            </form>
            </>}
 {page === 'orders' && <>
                {detail && <section className="card">
                <div className="section-title">
                <h2>{t("Заказ")}{" "}{detail.id.slice(0, 8)}
                </h2>
                <span className="badge">
                {detail.status === 'submitted' ? t("На рассмотрении, зарезервирован") : status(detail.status)}
                </span>
                </div>
                <p>{t("Сумма:")}{" "}<strong>
                {money(detail.total_amount)}
                </strong>
                </p>
                <p>{t("Поставка:")}{" "}{new Date(detail.requested_delivery_at).toLocaleString(locale(), { timeZone: 'Asia/Almaty' })}
                </p>
                    {detail.items.map((i: any) => <div className="order-row" key={i.product_id}>
                    <span>
                    {i.name} × {i.quantity}
                    </span>
                    <strong>
                    {money(i.line_total_amount)}
                    </strong>
                    </div>)}<p className="muted">{t("Резерв до:")}{" "}{detail.reservation_expires_at ? new Date(detail.reservation_expires_at).toLocaleString(locale(), { timeZone: 'Asia/Almaty' }) : t("не указан")}
                </p>
                <p>{status(detail.payment_status||"unpaid")}{t("· К погашению:")}{" "}<strong className={Number(detail.outstanding_amount) > 0 ? 'debt-value positive' : undefined}>{money(detail.outstanding_amount||"0")}</strong></p><OrderEvidence order={detail}/><CustomerOrderActions key={detail.id} order={detail} onChanged={() => { load(); loadDetail(detail.id); }}/>
                </section>}<section className="card">
            <h2>{t("История заказов")}</h2>
            {!orders.length && !loading && <p className="empty">{t("Пока нет заказов. Начните с каталога.")}</p>}{orders.map(o => <button className="order-row order-button" key={o.id} onClick={() => loadDetail(o.id)}>
                <span>№ {o.id.slice(0, 8)}<small>
                {new Date(o.created_at).toLocaleDateString(locale(), { timeZone: 'Asia/Almaty' })} · {status(o.status)}
                </small>
                </span>
                <strong>
                {money(o.total_amount)} →</strong>
                </button>)}
            </section>
            <RefundObligations revision={detail?.version||0}/>
            </>}
 {page === 'orders' && <>{orderCursor&&<button disabled={loading} onClick={()=>load(true)}>{t("Показать ещё заказы")}</button>}<CustomerReturns /></>}
 {page === 'debt' && balance && <>
            <div className="metrics">
                {[[t("Текущая задолженность"), 'debt_amount'], [t("Зарезервировано"), 'reserved_credit_amount'], [t("Доступная отсрочка"), 'available_credit_amount'], [t("Аванс"), 'advance_amount'],[t('Ожидает возврата'),'reserved_refund_amount']].map(([title, k]) => <section className="card metric" key={k}>
                <p>
                {title}
                </p>
                <strong className={k === 'debt_amount' && Number(balance[k]) > 0 ? 'debt-value positive' : undefined}>
                {money(balance[k])}
                </strong>
                </section>)}
            </div>
            <section className="card">
            <h2>{t("Условия расчётов")}</h2>
            <div className="order-row">
            <span>{t("Лимит отсрочки")}</span>
            <strong>
            {money(balance.credit_limit_amount)}
            </strong>
            </div>
            <div className="order-row">
            <span>{t("Период")}</span>
            <strong>
            {t('Дней: {{count}}', {count: balance.period_days})}</strong>
            </div>
            <div className="order-row">
            <span>{t("Текущий период, конец не включён")}</span>
            <strong>
            {balance.period_start} — {balance.period_end_exclusive}
            </strong>
            </div>
            <div className="order-row">
            <span>{t("Просрочено")}</span>
            <strong className={Number(balance.overdue_amount) > 0 ? 'debt-value positive' : undefined}>
            {money(balance.overdue_amount)}
            </strong>
            </div>
            <p className="muted">{t("Резерв уменьшает доступный лимит. Начисление долга происходит при передаче товара.")}</p>
            </section>
            </>}
 {page === 'payments' && <Payments />}
 {page === 'profile' && <CustomerProfile />}
 {page === 'points' && <DeliveryPoints />}
 {page === 'reports' && <Reports />}
 {page === 'notifications' && <Notifications />}
        </>}<SiteFooter customer/>
    </main>
    </div>;
}
const appRoot = import.meta.hot?.data.appRoot || createRoot(document.getElementById('root')!);
if (import.meta.hot) import.meta.hot.data.appRoot = appRoot;
appRoot.render(<React.StrictMode>
<App />
</React.StrictMode>);
