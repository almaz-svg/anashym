import React, { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { apiRequest } from './api';
import { ErrorBox, FieldsForm, money, notificationText, status, useCollection, useOperations } from './workspace';
import { t, locale } from './preferences';

export const dateTime = (value: string) => value ? new Date(value).toLocaleString(locale(), {timeZone:'Asia/Almaty'}) : '—';
export function NotificationMessage({ item }: {item:any}) {
 return <>{notificationText(item.message || item.event || item.title)}{item.payload?.overdue_amount && <> · {item.payload.client_name} · <strong className="debt-value positive">{money(item.payload.overdue_amount)}</strong></>}</>;
}
export function NotificationBell({onOpen}:{onOpen?:()=>void}) {
 const [items,setItems]=useState<any[]>([]), [open,setOpen]=useState(false), [error,setError]=useState<unknown>(null), [fresh,setFresh]=useState<any>(null);
 const known=useRef<Set<string>|null>(null),op=useOperations();
 useEffect(()=>{
  let stopped=false,pending=false;
  async function poll(){
   if(pending||document.visibilityState==='hidden')return;pending=true;
   try{const result=await apiRequest('/notifications?limit=100');if(stopped)return;
    const rows=result.items||[], incoming=rows.find((item:any)=>!item.read&&!item.read_at&&!known.current?.has(item.id));
    if(known.current&&incoming)setFresh(incoming);known.current=new Set(rows.map((item:any)=>item.id));setItems(rows);setError(null);
   }catch(e){if(!stopped)setError(e)}finally{pending=false}
  }
  void poll();const timer=setInterval(poll,10000);window.addEventListener('bakery:data-changed',poll);document.addEventListener('visibilitychange',poll);
  return()=>{stopped=true;clearInterval(timer);window.removeEventListener('bakery:data-changed',poll);document.removeEventListener('visibilitychange',poll)};
 },[op.revision]);
 const unread=items.filter(item=>!item.read&&!item.read_at);
 return <div className="notification-center">
  <button className="notification-toggle" type="button" title={t('Уведомления')} aria-label={t('Уведомления: {{count}} непрочитанных',{count:unread.length})} aria-expanded={open} onClick={()=>{setOpen(!open);setFresh(null)}}><Bell size={18}/>{!!unread.length&&<span className="notification-count">{unread.length}</span>}</button>
  {fresh&&!open&&<div className="notification-toast" role="status"><NotificationMessage item={fresh}/><button type="button" onClick={()=>setFresh(null)} aria-label={t('Закрыть')}>×</button></div>}
  {open&&<section className="notification-popover card" aria-label={t('Новые события')}>
   <h2>{t('Уведомления')}</h2><ErrorBox error={error||op.error}/>
   {!unread.length&&<p>{t('Пока нет новых событий.')}</p>}
   {unread.slice(0,8).map(item=><article key={item.id}><p><NotificationMessage item={item}/></p><small>{dateTime(item.created_at)}</small><button type="button" disabled={op.busy} onClick={()=>op.act('/notifications/'+item.id+'/read',{}).catch(()=>{})}>{t('Прочитано')}</button></article>)}
   <a href="#notifications" onClick={()=>{setOpen(false);onOpen?.()}}>{t('Все уведомления')}</a>
  </section>}
 </div>;
}

export function PasswordChange({onChanged,logout}:{onChanged:()=>void;logout:()=>void}) {
 const op=useOperations();
 return <main className="password-change card"><h1>{t('Установите новый пароль')}</h1><p>{t('Администратор сбросил доступ. Смените пароль, чтобы продолжить работу.')}</p>
 <FieldsForm title={t('Смена пароля')} fields={[{name:'current_password',label:'Текущий пароль',type:'password'},{name:'password',label:'Новый пароль, не менее 12 символов',type:'password'}]} onSubmit={async data=>{await op.act('/auth/change-password',data);onChanged()}} busy={op.busy} submit="Сменить пароль"/>
 <button type="button" onClick={logout}>{t('Выйти')}</button></main>;
}
export function ResetAccess({user,op}:{user:any;op:ReturnType<typeof useOperations>}) {
 const [result,setResult]=useState<any>(null);
 return <div className="access-actions"><button type="button" disabled={op.busy} onClick={async()=>{try{setResult(await op.act('/staff/'+user.id+'/reset-access',{}))}catch{}}}>{t('Сбросить доступ')}</button>
 {result&&<p className="notice">{t('Код восстановления доступа:')} <code>{result.invitation_token}</code><br/>{t('Передайте код владельцу аккаунта. Он действует 24 часа и используется для установки нового пароля.')}</p>}</div>;
}
export function ClientMembers({client}:{client:any}) {
 const op=useOperations(),data=useCollection('/clients/'+client.id+'/members',op.revision);
 return <details className="card"><summary>{t('Сотрудники клиента')} · {client.name}</summary><ErrorBox error={data.error||op.error}/>
 {data.items.map(user=><article className="member-row" key={user.id}><strong>{user.name||user.phone}</strong><span>{user.phone}</span><ResetAccess user={user} op={op}/></article>)}
 <FieldsForm title={t('Пригласить сотрудника клиента')} fields={[{name:'phone',label:'Телефон +7…',type:'tel'},{name:'name',label:'Имя'}]} onSubmit={data=>op.act('/clients/'+client.id+'/members',data)} busy={op.busy}/></details>;
}

export function ProtectedPhoto({photo}:{photo:any}) {
 const [url,setUrl]=useState(''),[error,setError]=useState<unknown>(null),[busy,setBusy]=useState(false);
 useEffect(()=>()=>{if(url)URL.revokeObjectURL(url)},[url]);
 async function load(){setBusy(true);setError(null);try{const data=await apiRequest('/files/'+photo.id);const response=await fetch(data.url,{credentials:'include'});if(!response.ok)throw new Error(t('Не удалось открыть защищённое фото'));setUrl(URL.createObjectURL(await response.blob()))}catch(e){setError(e)}finally{setBusy(false)}}
 return <figure className="proof-figure">{url?<a href={url} target="_blank" rel="noreferrer"><img src={url} alt={t('Фото подтверждения')}/></a>:<button type="button" disabled={busy} onClick={load}>{t(busy?'Загружаем…':'Открыть фото подтверждения')}</button>}<figcaption>{status(photo.purpose||'payment')} · {dateTime(photo.created_at)}</figcaption><ErrorBox error={error}/></figure>;
}
export function OrderEvidence({order}:{order:any}) {
 return <div className="order-evidence"><dl className="profile-details"><div><dt>{t('Способ оплаты')}</dt><dd>{status(order.payment_mode)}</dd></div><div><dt>{t('Срок оплаты')}</dt><dd>{dateTime(order.payment_due_at)}</dd></div></dl>
 {order.refund_obligation&&<p className="notice">{t('Обязательство возврата')}: {money(order.refund_obligation.amount)} · {status(order.refund_obligation.status)}</p>}
 {!!order.photos?.length&&<details><summary>{t('Фотографии заказа')} ({order.photos.length})</summary><div className="proof-gallery">{order.photos.map((photo:any)=><ProtectedPhoto key={photo.id} photo={photo}/>)}</div></details>}
 <details><summary>{t('История событий')}</summary>{!order.history?.length&&<p>{t('Записей пока нет.')}</p>}{order.history?.map((event:any,index:number)=><article className="event-row" key={event.id||index}><strong>{notificationText(event.action||event.event||event.type||event.status)}</strong><small>{dateTime(event.created_at)} · {event.actor_name||event.actor?.name||t('Система')}</small>{(event.reason||event.details?.reason)&&<p>{event.reason||event.details.reason}</p>}<details><summary>{t('Подробнее')}</summary><ChangeSummary before={event.before} after={event.after}/></details></article>)}</details>
 </div>;
}
const changeLabels:Record<string,string>={approval_status:'Доступ',deferred_approved:'Отсрочка одобрена',credit_limit:'Лимит отсрочки',period_days:'Период, дней',status:'Статус',state:'Состояние проверки',name:'Название',quantity:'Количество',price:'Цена',price_amount:'Цена',amount:'Сумма',payment_mode:'Способ оплаты',requested_delivery_at:'Дата доставки',is_active:'Активен',active:'Активен',archived:'В архиве',role:'Роль',balance:'Баланс',reason:'Причина',reversal_reason:'Причина сторнирования',available_qty:'Доступно порций',shelf_life_hours:'Срок хранения, часов',description:'Описание',courier_name:'Курьер',client_name:'Клиент'};
function displayValue(value:any):string {if(value==null)return '—';if(typeof value==='boolean')return t(value?'Да':'Нет');if(Array.isArray(value))return value.map(displayValue).join(', ');if(typeof value==='object')return Object.entries(value).map(([key,item])=>`${t(changeLabels[key]||key)}: ${displayValue(item)}`).join(' · ');return status(String(value));}
export function ChangeSummary({before,after}:{before:any;after:any}) {
 if(!before&&!after)return null;
 const keys=[...new Set([...Object.keys(before||{}),...Object.keys(after||{})])].filter(key=>!/password|token|secret/i.test(key));
 return <div className="audit-changes">{keys.map(key=><div className="audit-change" key={key}><strong>{t(changeLabels[key]||key)}</strong><span><small>{t('До')}</small>{displayValue(before?.[key])}</span><span><small>{t('После')}</small>{displayValue(after?.[key])}</span></div>)}</div>;
}
export function AuditTrail(){const data=useCollection('/audit?limit=20');return <><ErrorBox error={data.error}/><section className="card"><h2>{t('Журнал действий')}</h2>{data.items.map(event=><article className="event-row" key={event.id}><h3>{notificationText(event.action)}</h3><p>{dateTime(event.created_at)} · {event.actor_name||event.actor?.name||event.actor_phone||t('Система')}</p><p>{event.client_name||event.object_name||event.object_type} {event.object_id&&<small>№{String(event.object_id).slice(0,8)}</small>}</p>{(event.reason||event.details?.reason)&&<p><strong>{t('Причина')}: </strong>{event.reason||event.details.reason}</p>}<ChangeSummary before={event.before||event.details?.before} after={event.after||event.details?.after}/>{!event.before&&!event.after&&event.details&&<ChangeSummary before={null} after={event.details}/>}</article>)}{!data.loading&&!data.items.length&&<p>{t('Записей пока нет.')}</p>}{data.nextCursor&&<button disabled={data.loading} onClick={()=>data.loadMore()}>{t('Показать ещё')}</button>}</section></>}
