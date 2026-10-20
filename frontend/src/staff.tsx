import { t, locale } from './preferences';
import { AdminOrder } from './admin-order';
import { PDF_PRODUCT_PHOTOS } from './product-photos';
import { OrderPanel } from './order-workspace';
import React, { useEffect, useRef, useState } from 'react';
import { BrandLogo } from './brand-logo';
import { AccountHeader, SiteFooter } from './account-shell';
import { ErrorBox, FieldsForm, Records, useCollection, useOperations, PhotoUpload, money, status, Field, WorkspaceRevision } from './workspace';
import { Reports, Notifications, CustomerOrderActions } from './customer';
import { AuditTrail, ClientMembers, ResetAccess, ProtectedPhoto } from './account-features';
import { apiRequest, ApiError } from './api';
import { useLiveRefresh } from './live-refresh';
import { OrderRowSummary } from './order-summary';
const roleNames: Record<string, string> = { admin: 'Администратор', courier: 'Курьер', cashier: 'Кассир', accountant: 'Бухгалтер' };
const menus: Record<string, string[][]> = { admin: [['orders', 'Заказы'], ['catalog', 'Каталог и склад'], ['clients', 'Клиенты'], ['staff', 'Сотрудники'], ['payments', 'Платежи'], ['returns', 'Возвраты'], ['refunds','Возврат денег'], ['audit', 'Журнал'], ['reports', 'Отчёты']], courier: [['orders', 'Задания'], ['handovers', 'Сдача наличных'], ['returns', 'Возврат товара'], ['reports','Мой отчёт']], cashier: [['payments', 'Проверка Kaspi'], ['orders','Заказы'], ['catalog','Каталог'], ['handovers', 'Приём наличных'], ['shifts', 'Смены'], ['refunds', 'Возврат денег'], ['reports','Мой отчёт']], accountant: [['ledger', 'Реестр операций'], ['orders','Заказы'], ['catalog','Каталог'], ['clients', 'Клиенты'], ['periods', 'Расчётные периоды'], ['payments', 'Платежи'], ['returns','Возвраты'], ['reports', 'Отчёты'], ['refunds', 'Возврат денег'], ['cash', 'Касса']] };
export function StaffWorkspace({ user, logout, busy, sessionError }: {
    user: any;
    logout: () => void;
    busy?: boolean;
    sessionError?: unknown;
}) {
    const role = user.role;
    function allowedPage(hash:string){const requested=hash.replace(/^#/, '');return requested==='notifications'||menus[role]?.some(([id])=>id===requested)?requested:menus[role]?.[0][0]||'orders';}
    const [route,setRoute]=useState(()=>allowedPage(location.hash));
    const page=allowedPage('#'+route);
    function navigate(id:string){const next=allowedPage('#'+id);if(location.hash!=='#'+next)history.pushState(null,'','#'+next);setRoute(next);}
    useEffect(()=>{
        function sync(){const next=allowedPage(location.hash);if(location.hash!=='#'+next)history.replaceState(null,'','#'+next);setRoute(next);}
        sync();window.addEventListener('hashchange',sync);window.addEventListener('popstate',sync);
        return()=>{window.removeEventListener('hashchange',sync);window.removeEventListener('popstate',sync);};
    },[role]);
    useEffect(() => { window.scrollTo(0, 0); }, [page]);
    const op = useOperations();
    return <WorkspaceRevision.Provider value={op.revision}><div className="shell">
    <aside>
    <a className="brand" href="#">
    <BrandLogo/></a>
    <span className="eyebrow">
    {t(roleNames[role])}
    </span>
    <nav>
        {(role==='admin' ? menus.admin.filter(([id])=>['orders','clients','catalog','payments','staff'].includes(id)).sort((a,b)=>['orders','clients','catalog','payments','staff'].indexOf(a[0])-['orders','clients','catalog','payments','staff'].indexOf(b[0])) : menus[role])?.map(([id, label]) => <a href={'#' + id} key={id} className={id === page ? 'active' : ''} onClick={e => { e.preventDefault(); navigate(id); }}>
        {t(label)}
        </a>)}
        {role==='admin' ? <details open={['returns','refunds','audit','reports','notifications'].includes(page) || undefined}><summary>{t('Дополнительно')}</summary>
        {menus.admin.filter(([id])=>!['orders','clients','catalog','payments','staff'].includes(id)).map(([id,label])=><a href={'#'+id} key={id} className={id===page?'active':''} onClick={e=>{e.preventDefault();navigate(id)}}>{t(label)}</a>)}
        <a href="#notifications" className={page==='notifications'?'active':''} onClick={e=>{e.preventDefault();navigate('notifications')}}>{t('Уведомления')}</a>
        </details> : <a href="#notifications" onClick={e => { e.preventDefault(); navigate('notifications'); }}>{t("Уведомления")}</a>}
    </nav>
    </aside>
    <main className="content">
    <AccountHeader user={user} logout={logout} busy={busy} staffRole={roleNames[role]} onNotifications={()=>navigate('notifications')} onDebt={()=>navigate(role==='admin'||role==='accountant'?'clients':'orders')}/>
    <ErrorBox error={sessionError}/>
    <div className="page-title">
    <h1>
    {t(menus[role]?.find(x => x[0] === page)?.[1] || 'Уведомления')}
    </h1>
    <button onClick={() => op.refresh()}>{t("Обновить")}</button>
    </div>
    <ErrorBox error={op.error}/>
    {page === 'orders' ? <Orders role={role} revision={op.revision}/> : page === 'catalog' ? <Catalog editable={role==='admin'}/> : page === 'clients' ? <Clients editable={role === 'admin'}/> : page === 'staff' ? <Staff /> : page === 'payments' ? <Payments role={role}/> : page === 'handovers' ? <Handovers role={role}/> : page === 'shifts' ? <Shifts /> : page === 'returns' ? <Returns role={role}/> : page === 'refunds' ? <Refunds role={role}/> : page === 'audit' ? <AuditTrail/> : page === 'cash' ? <>
        <CashWallet revision={op.revision}/>
        <Collection path='/cash-movements' title={t("Движения наличных")} revision={op.revision}/>
        </> : page === 'periods' ? <Periods /> : page === 'reports' ? <Reports own={['courier','cashier'].includes(role)}/> : page === 'notifications' ? <Notifications /> : <Collection path={'/' + page} title={t(menus[role]?.find(x => x[0] === page)?.[1] || page)} revision={op.revision}/>}<SiteFooter/>
    </main>
    </div></WorkspaceRevision.Provider>;
}
function Collection({ path, title, revision = 0 }: {
    path: string;
    title: string;
    revision?: number;
}) {
    const data = useCollection(path, revision, 5000);
    return <>
    <ErrorBox error={data.error}/>
    {data.loading && <p role="status">{t("Загружаем…")}</p>}<Records items={data.items} title={title}/>{data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}
    </>;
}
function Orders({ role, revision }: {
    role: string;
    revision: number;
}) {
    const [history,setHistory]=useState('active');
    const op = useOperations(), data = useCollection('/orders?limit=20'+(role==='courier'?'&history='+history:''), revision + op.revision,5000), [selected, setSelected] = useState<any>(null);
    const detailRequest=useRef(0);
    async function refreshSelected(live:()=>boolean){
        const id=selected?.id;if(!id)return;
        const request=++detailRequest.current;
        try{
            const result=await apiRequest('/orders/'+id);
            if(live()&&request===detailRequest.current)setSelected((old:any)=>old?.id===id&&result.version>=old.version?result:old);
        }catch(error){
            if(live()&&request===detailRequest.current){
                if(error instanceof ApiError&&[403,404].includes(error.status))setSelected(null);
                op.setError(error);
            }
        }
    }
    useEffect(()=>{let active=true;void refreshSelected(()=>active);return()=>{active=false;detailRequest.current++}},[selected?.id,op.revision,revision,role]);
    useEffect(()=>{setSelected(null)},[role]);
    useLiveRefresh(refreshSelected,!!selected,5000,selected?.id+':'+role+':'+revision+':'+op.revision);
    return <>
    <ErrorBox error={data.error || op.error}/>
    {role === 'admin' && <AdminOrder op={op}/>}
    {role==='courier'&&<div className="button-row" aria-label={t('Доставки')}><button aria-pressed={history==='active'} onClick={()=>{setHistory('active');setSelected(null)}}>{t('Текущие')}</button><button aria-pressed={history==='delivered'} onClick={()=>{setHistory('delivered');setSelected(null)}}>{t('Выполненные')}</button></div>}
    <section className="card">
    <h2>
    {t(role === 'courier' ? history==='delivered'?'Выполненные доставки':'Назначенные доставки' : 'Очередь заказов')}
    </h2>
    {!data.items.length && <p>{t("Нет заказов.")}</p>}{data.items.map(o => <button key={o.id} className="order-row order-button" onClick={() => setSelected(o)}>
        <span>№{o.id.slice(0, 8)} · {status(o.status)}<small>
        {new Date(o.requested_delivery_at).toLocaleString(locale(), { timeZone: 'Asia/Almaty' })} · {o.client_name || o.client_id}
        </small>
        <OrderRowSummary order={o}/>
        </span>
        <strong>
        {money(o.total_amount)}
        </strong>
        </button>)}{data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t("Показать ещё заказы")}</button>}
    </section>
    {selected && <OrderPanel key={selected.id} order={selected} role={role} op={op} close={() => setSelected(null)}/>}
    </>;
}
function Payments({ role }: {
    role: string;
}) {
    const op = useOperations(), data = useCollection('/payments', op.revision,5000);
    return <>
    <ErrorBox error={op.error || data.error}/>
    {role==='cashier'&&<Orders role={role} revision={op.revision}/>}
    <Records items={data.items} title={t("Платежи")}/>
        {['admin', 'cashier', 'accountant'].includes(role) && data.items.filter(p => (p.status || p.state) === 'pending').map(p => <section className="card" key={p.id}>
        <h3>{t("Проверка")}{' '}{money(p.amount || p.amount_amount)}
        </h3>
        <p>
        {p.reference} · {p.client_name || t('Клиент')} · №{p.order_id?.slice(0,8)}
        </p>
        {(p.proof_id||p.proof?.id)&&<ProtectedPhoto photo={p.proof||{id:p.proof_id,purpose:'payment',created_at:p.created_at}}/>}
        <FieldsForm title={t("Результат сверки")} fields={[{ name: 'reason', label: 'Комментарий проверки' }]} onSubmit={d => op.act('/payments/' + p.id + '/confirm', d)} busy={op.busy} submit={t("Подтвердить платёж")}/>
        <FieldsForm title={t('Отклонение платежа')} fields={[{name:'reason',label:'Причина'}]} onSubmit={d=>op.act('/payments/'+p.id+'/reject',d)} busy={op.busy} submit="Отклонить"/>
        </section>)}
        {['admin','accountant'].includes(role)&&data.items.filter(p=>p.status==='confirmed').map(p=><details className="card" key={p.id}><summary>{t('Сторнирование платежа')} · {p.client_name} · {money(p.amount)}</summary><p className="muted">{t('Сторнирование отменит финансовый эффект подтверждённого платежа и сохранит историю.')}</p><FieldsForm title={t('Сторнировать платёж')} fields={[{name:'reason',label:'Причина сторнирования'}]} onSubmit={data=>op.act('/payments/'+p.id+'/reverse',data)} busy={op.busy} submit="Сторнировать платёж"/></details>)}
        {data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}
    </>;
}
function Handovers({ role }: {
    role: string;
}) {
    const op = useOperations(), data = useCollection('/handovers', op.revision,5000);
    return <>
    <ErrorBox error={op.error || data.error}/>
    {role === 'courier' && <FieldsForm title={t("Передать наличные в кассу")} fields={[{ name: 'amount', label: 'Сумма, KZT', type: 'number', step: '0.01' }]} onSubmit={d => op.act('/handovers', d)} busy={op.busy}/>}{role === "courier" && <CashWallet revision={op.revision}/>}<Records items={data.items} title={t("Передачи наличных")}/>
    {role === 'cashier' && data.items.filter(h => h.status === 'pending').map(h => <FieldsForm key={h.id} title={t('Приём №{{number}}', { number: h.id.slice(0, 8) })} fields={[{ name: 'amount', label: 'Фактически принято, KZT', type: 'number', value: h.amount || h.amount_amount, step: '0.01' }, { name: 'reason', label: 'Комментарий расхождения', required: false }]} onSubmit={d => op.act('/handovers/' + h.id + '/confirm', d)} busy={op.busy}/>)}
    </>;
}
function Shifts() {
    const op = useOperations();
    return <>
    <ErrorBox error={op.error}/>
    <section className="card">
    <h2>{t("Кассовая смена")}</h2>
    <div className="button-row">
    <FieldsForm title={t("Открытие смены")} fields={[{ name: 'opening_amount', label: 'Начальный остаток в кассе KZT', type: 'number', step: '0.01', value: '0' }]} onSubmit={d => op.act('/shifts', { ...d, action: 'open' })} busy={op.busy} submit={t("Открыть смену")}/>
    </div>
    </section>
    <FieldsForm title={t("Закрытие с фактическим остатком")} fields={[{ name: 'counted_amount', label: 'Фактически в кассе KZT', type: 'number', step: '0.01' }, { name: 'reason', label: 'Причина расхождения', required: false }]} onSubmit={d => op.act('/shifts', { ...d, action: 'close' })} busy={op.busy}/>
    <FieldsForm title={t("Подотчёт курьеру")} fields={[{ name: 'courier_id', label: 'Курьер' }, { name: 'amount', label: 'Сумма KZT', type: 'number', step: '0.01' }, { name: 'direction', label: 'Направление', options: [['issue', 'Выдать'], ['return', 'Вернуть в кассу']] }, { name: 'reason', label: 'Основание' }]} onSubmit={d => op.act('/cash-movements', d)} busy={op.busy}/>
    <Collection path="/shifts" title={t("История смен")} revision={op.revision}/>
    </>;
}
function Returns({ role }: {
    role: string;
}) {
    const op = useOperations(), data = useCollection('/returns', op.revision), orders=useCollection(role==='courier'?'/orders?limit=20':'',op.revision),[orderId,setOrderId]=useState('');
    return <>
    <ErrorBox error={op.error || data.error}/>
    {role==='courier'&&<section className="card"><h2>{t('Создать возврат или обмен')}</h2><ErrorBox error={orders.error}/><label>{t('Заказ')}<select value={orderId} onChange={e=>setOrderId(e.target.value)}><option value="">{t('Выберите…')}</option>{orders.items.filter(o=>['delivered','partially_delivered'].includes(o.status)).map(o=><option key={o.id} value={o.id}>{o.client_name} · №{o.id.slice(0,8)} · {money(o.total_amount)}</option>)}</select></label>{orders.nextCursor&&<button disabled={orders.loading} onClick={()=>orders.loadMore()}>{t('Показать ещё заказы для выбора')}</button>}{orderId&&orders.items.some(o=>o.id===orderId)&&<CustomerOrderActions key={orderId} order={orders.items.find(o=>o.id===orderId)} onChanged={op.refresh} returnsOnly/>}</section>}
    <Records items={data.items} title={t("Возвраты и обмены")}/>
        {data.items.filter(r => r.status === 'pending' || (r.status === 'approved' && !r.received)).map(r => <section className="card" key={r.id}>
        <h3>{t("Заявка №")}{r.id.slice(0, 8)} · {money(r.amount)}
        </h3>
        <p>
        {r.reason}
        </p>
        {!r.received && ['admin','courier'].includes(role) && <ReturnReceive record={r} op={op}/>}{role === 'admin' && r.status === 'pending' && <FieldsForm title={t("Финансовое решение")} fields={[{ name: 'decision', label: 'Решение', options: [['approve', 'Одобрить'], ['reject', 'Отклонить']] }, { name: 'disposition', label: 'Учёт товара', options: [['quarantine', 'Карантин'], ['write_off', 'Списание']] }, { name: 'without_collection', label: 'Физический приём', options: [['false', 'Товар принят / будет принят'], ['true', 'Одобрить без возврата товара']] }, { name: 'reason', label: 'Основание' }]} onSubmit={d => op.act('/returns/' + r.id + '/decide', { ...d, without_collection: d.without_collection === 'true' })} busy={op.busy}/>}
        </section>)}{data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}
    </>;
}
function ReturnReceive({ record: r, op }: {
    record: any;
    op: ReturnType<typeof useOperations>;
}) {
    const [photos, setPhotos] = useState<string[]>([]);
    return <form onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            try {
                await op.act('/returns/' + r.id + '/receive', { reason: f.get('reason'), photo_ids: photos });
                setPhotos([]);
            }
            catch { }
        }}>
    <h3>{t("Фактический приём в карантин")}</h3>
    <label>{t("Комментарий")}<input name="reason" required/>
    </label>
    <PhotoUpload orderId={r.order_id} purpose={r.kind || 'return'} onUploaded={id => setPhotos(p => [...p, id])} act={op.act} busy={op.busy}/>
    <button disabled={op.busy || !photos.length}>{t("Подтвердить приём товара")}</button>
    </form>;
}
function Refunds({ role }: {
    role: string;
}) {
    const op = useOperations(), data = useCollection('/refunds', op.revision);
    return <>
    <ErrorBox error={op.error || data.error}/>
    <FieldsForm title={t("Оформить возврат денег")} fields={[{ name: 'client_id', label: 'Клиент' }, { name: 'amount', label: 'Сумма KZT', type: 'number', step: '0.01' }, { name: 'method', label: 'Способ', options: [['kaspi', 'Kaspi'], ['cash', 'Наличные']] }, { name: 'reason', label: 'Основание' }]} onSubmit={d => op.act('/refunds', d)} busy={op.busy}/>
    <Records items={data.items} title={t("Обязательства возврата")}/>
    {data.items.filter(r => r.status === 'pending' && ['admin','cashier','accountant'].includes(role)).map(r => <FieldsForm key={r.id} title={t('Возврат №{{number}}', { number: r.id.slice(0, 8) })} fields={[{ name: 'reference', label: 'Номер перевода / кассовый документ' }, { name: 'reason', label: 'Основание' }]} onSubmit={d => op.act('/refunds/' + r.id + '/confirm', d)} busy={op.busy}/>)}
    </>;
}
function Catalog({editable}:{editable:boolean}) {
    const op = useOperations(), products = useCollection("/products", op.revision);
    const [archived,setArchived]=useState(false);
    if(!editable)return <><ErrorBox error={products.error}/><div className="products">{products.items.filter(p=>p.active!==false).map(p=><article className="card product" key={p.id}>{p.image_url&&<img className="catalog-photo" src={p.image_url} alt={p.name}/>}<h2>{p.name}</h2><p>{p.description}</p><strong>{money(p.price_amount)}</strong><p>{t('Срок хранения, часов')}: {p.shelf_life_hours??'—'}</p><p>{t('Доступные даты')}: {p.available_dates?.join(', ')||'—'}</p><p>{t('Доступно порций: {{count}} · {{minutes}} мин',{count:p.available_qty||0,minutes:p.preparation_minutes})}</p></article>)}</div>{products.nextCursor&&<button onClick={()=>products.loadMore()}>{t('Показать ещё')}</button>}</>;
    return <>
    <ErrorBox error={op.error || products.error}/>
    <details className="card"><summary>{t("Добавить товар")}</summary><FieldsForm title={t("Новый товар")} fields={[{ name: 'name', label: 'Название' }, { name: 'description', label: 'Описание' }, { name:'image_url',label:'Ссылка на фото',type:'url',required:false },{name:'shelf_life_hours',label:'Срок хранения, часов',type:'number',value:'72'}, { name: 'price_amount', label: 'Цена, KZT', type: 'number', step: '0.01' }, { name: 'preparation_minutes', label: 'Время подготовки, мин', type: 'number' }]} onSubmit={d => op.act('/products', d)} busy={op.busy}/></details>
    <label className="checkbox-label"><input type="checkbox" checked={archived} onChange={e=>setArchived(e.target.checked)}/>{t('Показать архив')}</label>
        {products.items.filter(p => archived||p.active !== false).map(p => <article className="card" key={p.id}>
        <div className="order-row"><h2>{p.name}</h2><strong>{money(p.price_amount ?? p.price)}</strong></div>
        <p>{t('Доступно порций: {{count}} · {{minutes}} мин', {count:p.available_qty ?? 0, minutes:p.preparation_minutes})}{p.active===false && <> · {t('Архив')}</>}</p>
        <details><summary>{t("Изменить товар")}</summary>
        {p.image_url&&<img className="catalog-photo" src={p.image_url} alt={p.name}/>}
        <fieldset disabled={op.busy}><legend>{t("Выбрать фото товара")}</legend><div className="product-photo-picker">{PDF_PRODUCT_PHOTOS.map(photo=><button type="button" key={photo.src} aria-label={photo.label} aria-pressed={p.image_url===new URL(photo.src,window.location.origin).href} onClick={()=>op.act('/products/'+p.id,{image_url:new URL(photo.src,window.location.origin).href}).catch(()=>{})}><img src={photo.src} alt={photo.label}/><span>{photo.label}</span></button>)}</div></fieldset>
        <FieldsForm title={t("Карточка товара")} fields={[{ name: "name", label: "Название", value: p.name }, { name: "description", label: "Описание", value: p.description, required: false }, {name:'image_url',label:'Ссылка на фото',type:'url',required:false,value:p.image_url||''},{name:'shelf_life_hours',label:'Срок хранения, часов',type:'number',value:String(p.shelf_life_hours??72)}, { name: "price_amount", label: "Цена KZT", type: "number", step: "0.01", value: p.price_amount || p.price }, { name: "preparation_minutes", label: "Подготовка, минут", type: "number", value: String(p.preparation_minutes) }]} onSubmit={d => op.act("/products/" + p.id, d)} busy={op.busy}/>
        <button disabled={op.busy} onClick={()=>op.act('/products/'+p.id+(p.active===false?'/restore':'/archive'),{}).catch(()=>{})}>{t(p.active===false?'Восстановить из архива':'Архивировать товар')}</button>
        </details></article>)}
    {products.nextCursor&&<button disabled={products.loading} onClick={()=>products.loadMore()}>{t('Показать ещё')}</button>}
    <details className="card"><summary>{t("Склад и производство")}</summary><FieldsForm title={t("Партия готовой продукции")} fields={[{ name: 'product_id', label: 'Товар' }, { name: 'quantity', label: 'Порций', type: 'number' }, { name: 'manufactured_at', label: 'Изготовлено', type: 'datetime-local' }, { name: 'expires_at', label: 'Годно до', type: 'datetime-local' }]} onSubmit={d => op.act('/batches', { ...d, manufactured_at: new Date(d.manufactured_at).toISOString(), expires_at: new Date(d.expires_at).toISOString() })} busy={op.busy}/>
    <Collection path="/batches" title={t("Партии")} revision={op.revision}/>
    <FieldsForm title={t("Корректировка партии")} fields={[{ name: 'batch_id', label: 'Партия' }, { name: 'quantity', label: 'Новый фактический остаток', type: 'number' }, { name: 'reason', label: 'Причина' }]} onSubmit={d => op.act('/batches/' + d.batch_id + '/adjust', { quantity: Number(d.quantity), reason: d.reason })} busy={op.busy}/>
    <FieldsForm title={t("Производственная квота")} fields={[{ name: 'product_id', label: 'Товар' }, { name: 'date', label: 'Дата поставки', type: 'date' }, { name: 'quantity', label: 'Порций', type: 'number' }, { name: 'cutoff', label: 'Приём заявок до', type: 'datetime-local' }]} onSubmit={d => op.act('/quotas', { ...d, cutoff: new Date(d.cutoff).toISOString() })} busy={op.busy}/>
    <Collection path="/quotas" title={t("Квоты")} revision={op.revision}/>
    <Quarantine /></details>
    </>;
}
function Clients({ editable }: {
    editable: boolean;
}) {
    const op = useOperations(), data = useCollection('/clients', op.revision, 10000),[archived,setArchived]=useState(false);
    return <>
    <ErrorBox error={data.error || op.error}/>
    <label className="checkbox-label"><input type="checkbox" checked={archived} onChange={e=>setArchived(e.target.checked)}/>{t('Показать архив')}</label>
    {!data.loading && !data.items.filter(c=>archived||!c.archived).length && <p>{t("Нет клиентов.")}</p>}
    {data.items.filter(c=>archived||!c.archived).map(c => <section className="card" key={c.id}>
    <div className="order-row"><div><h2>{c.name || t('Клиент')}</h2><p>{t(c.archived?'Архив':c.approval_status==='rejected'?'Доступ отклонён':'Доступ открыт')}</p></div><div><span>{t('Долг')}</span><strong>{money(c.debt_amount ?? 0)}</strong></div></div>
    {editable && <details><summary>{t('Настройки клиента')}</summary><Records items={[c]} title={t('Данные клиента')}/><FieldsForm key={c.id+':'+op.revision} title={c.name || t('Клиент')} fields={[{ name: 'approval_status', label: 'Доступ',value:c.approval_status, options: [['active', 'Открыт'], ['pending', 'Открыт (ранее зарегистрирован)'], ['rejected', 'Заблокирован']] }, { name: 'period_days', label: 'Расчётный период',value:String(c.period_days), options: [['7', '7 дней'], ['14', '14 дней'], ['30', '30 дней']] }, { name: 'period_start', label: 'Начало первого периода', type: 'date', value: c.period_start }, { name: 'reason', label: 'Основание' }]} onSubmit={d => op.act('/clients/' + c.id + '/approve', { approval_status: d.approval_status, period_days: Number(d.period_days), period_start: d.period_start, reason: d.reason })} busy={op.busy}/><ClientMembers client={c}/><button disabled={op.busy} onClick={()=>op.act('/clients/'+c.id+(c.archived?'/restore':'/archive'),{}).catch(()=>{})}>{t(c.archived?'Восстановить из архива':'Архивировать клиента')}</button></details>}{!editable && <details><summary>{t("Подробнее")}</summary><Records items={[c]} title={t("Данные клиента")}/></details>}</section>)}
    {data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}
    </>;
}
function Staff() {
    const op = useOperations(),data=useCollection('/staff',op.revision,10000);
    return <>
    <ErrorBox error={op.error}/>
    <details className="card"><summary>{t("Пригласить сотрудника")}</summary><FieldsForm title={t("Пригласить сотрудника")} fields={[{ name: 'phone', label: 'Логин или телефон', type: 'text' }, { name: 'name', label: 'Имя' }, { name: 'role', label: 'Роль', options: [['courier', 'Курьер'], ['cashier', 'Кассир'], ['accountant', 'Бухгалтер'], ['admin', 'Администратор']] }]} onSubmit={d => op.act('/staff', d)} busy={op.busy}/></details>
    <ErrorBox error={data.error}/>{data.items.map(user=><section className="card" key={user.id}><h3>{user.name||user.phone}</h3><p>{status(user.role)} · {user.phone}</p><details><summary>{t("Управление доступом")}</summary><ResetAccess user={user} op={op}/></details></section>)}{data.nextCursor&&<button onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}
    <details className="card"><summary>{t("Изменить роль сотрудника")}</summary><FieldsForm title={t("Изменить роль сотрудника")} fields={[{ name: 'user_id', label: 'Сотрудник' }, { name: 'role', label: 'Роль', options: [['courier', 'Курьер'], ['cashier', 'Кассир'], ['accountant', 'Бухгалтер'], ['admin', 'Администратор']] }]} onSubmit={d => op.act('/staff/' + d.user_id + '/role', { role: d.role })} busy={op.busy}/></details>
    </>;
}
function Periods() {
    const op = useOperations();
    return <>
    <ErrorBox error={op.error}/>
    <FieldsForm title={t("Закрыть завершённые расчётные периоды")} fields={[{ name: "as_of", label: "По дату", type: "date" }]} onSubmit={d => op.act("/periods/close", d)} busy={op.busy}/>
    <Collection path="/periods" title={t("Расчётные периоды")} revision={op.revision}/>
    </>;
}
function CashWallet({ revision }: {
    revision: number;
}) {
    const data = useCollection('/cash', revision,5000);
    return <>
    <ErrorBox error={data.error}/>
    <div className="metrics">
        {[['balance_amount', 'На руках'], ['available_amount', 'Можно сдать'], ['reserved_amount', 'Ожидает приёма']].map(([key, label]) => <section className="card metric" key={key}>
        <p>
        {t(label)}
        </p>
        <strong>
        {data.payload ? money(data.payload[key]) : '…'}
        </strong>
        </section>)}
    </div>
    </>;
}
function Quarantine() {
    const op = useOperations(), data = useCollection('/stock-movements', op.revision);
    return <>
    <ErrorBox error={data.error || op.error}/>
    <h2>{t("Карантин товара")}</h2>
        {data.items.filter(m => m.disposition === 'quarantine'&&!m.resolved).map(m => <section className="card" key={m.id}>
        <p>
        {t('{{count}} порций', { count: m.quantity })} · {m.reason}
        </p>
        <FieldsForm title={t("Решение по физическому товару")} fields={[{ name: 'disposition', label: 'Решение', options: [['available', 'Вернуть в годную партию'], ['write_off', 'Списать']] }, { name: 'batch_id', label: 'Годная партия (для возврата)', required: false }, { name: 'reason', label: 'Основание проверки' }]} onSubmit={d => op.act('/stock-movements/' + m.id + '/resolve', { ...d, batch_id: d.batch_id || undefined })} busy={op.busy}/>
        </section>)}
    </>;
}

