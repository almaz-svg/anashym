import {useEffect,useState} from 'react';
import {apiRequest} from './api';
import {money} from './workspace';
import {t} from './preferences';

export function DebtIndicator({user,onOpen}:{user:any;onOpen?:()=>void}) {
    const [amount,setAmount]=useState<string|null>(null),[failed,setFailed]=useState(false);
    const eligible=!user.must_change_password&&(['admin','accountant','cashier','courier'].includes(user.role)||(user.role==='customer'&&['active','pending'].includes(user.approval_status)));
    useEffect(()=>{
        setAmount(null);setFailed(false);
        if(!eligible)return;
        let stopped=false,pending=false;
        async function refresh(){
            if(pending||document.visibilityState==='hidden')return;
            pending=true;
            try {
                const result=await apiRequest('/debt-summary');
                if(!Number.isFinite(Number(result.debt_amount)))throw new Error('Invalid debt amount');
                if(!stopped){setAmount(result.debt_amount);setFailed(false)}
            }catch{if(!stopped)setFailed(true)}finally{pending=false}
        }
        void refresh();
        const timer=setInterval(refresh,5000);
        window.addEventListener('bakery:data-changed',refresh);
        document.addEventListener('visibilitychange',refresh);
        return()=>{stopped=true;clearInterval(timer);window.removeEventListener('bakery:data-changed',refresh);document.removeEventListener('visibilitychange',refresh)};
    },[eligible,user.user_id,user.role]);
    if(!eligible)return null;
    if(!(Number(amount)>0))return failed?<p className="muted" role="status">{t('Задолженность временно недоступна')}</p>:null;
    const label=t(user.role==='customer'?'Ваша задолженность':user.role==='courier'?'Задолженность по вашим доставкам':'Задолженность клиентов');
    return <section className="debt-indicator" aria-label={label}>
        <p>{label}</p><strong>{money(amount)}</strong>
        <div>{user.role==='customer'?<a href="#debt">{t('Подробнее')}</a>:onOpen&&<button type="button" onClick={onOpen}>{t('Подробнее')}</button>}</div>
        {failed&&<small role="status">{t('Не удалось обновить сумму')}</small>}
    </section>;
}
