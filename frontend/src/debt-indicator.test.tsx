// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {DebtIndicator} from './debt-indicator';

afterEach(()=>{cleanup();vi.unstubAllGlobals()});
const customer={user_id:'customer-1',role:'customer',approval_status:'active'};

it('shows one debt amount and hides it after a confirmed payment refresh',async()=>{
 let amount='2500.00';
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({debt_amount:amount,scope:'own',currency:'KZT'}))));
 render(<DebtIndicator user={customer}/>);
 await screen.findByRole('region',{name:'Ваша задолженность'});
 expect(screen.getAllByRole('region',{name:'Ваша задолженность'})).toHaveLength(1);
 expect(screen.getByRole('link',{name:'Подробнее'}).getAttribute('href')).toBe('#debt');
 amount='0.00';
 act(()=>window.dispatchEvent(new Event('bakery:data-changed')));
 await waitFor(()=>expect(screen.queryByRole('region',{name:'Ваша задолженность'})).toBeNull());
});

it('does not query restricted data for rejected customers',async()=>{
 const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
 render(<DebtIndicator user={{...customer,approval_status:'rejected'}}/>);
 expect(fetch).not.toHaveBeenCalled();
 expect(screen.queryByRole('region')).toBeNull();
});

it('opens the staff debt view and does not claim zero when fetching fails',async()=>{
 let fail=false;
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify(fail?{message:'Unavailable'}:{debt_amount:'6500.00',scope:'all_clients'}),{status:fail?503:200})));
 const open=vi.fn();render(<DebtIndicator user={{user_id:'admin',role:'admin'}} onOpen={open}/>);
 await screen.findByRole('region',{name:'Задолженность клиентов'});
 fireEvent.click(screen.getByRole('button',{name:'Подробнее'}));expect(open).toHaveBeenCalledOnce();
 fail=true;act(()=>window.dispatchEvent(new Event('bakery:data-changed')));
 await screen.findByText('Не удалось обновить сумму');
 expect(screen.getByRole('region',{name:'Задолженность клиентов'}).textContent).toContain('6');
});

it('shows debt for legacy pending customers with immediate purchasing access',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({debt_amount:'900.00',scope:'own'}))));
 render(<DebtIndicator user={{...customer,approval_status:'pending'}}/>);
 await screen.findByRole('region',{name:'Ваша задолженность'});
});
