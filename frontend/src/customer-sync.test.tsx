// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {App} from './main';

vi.mock('react-dom/client',()=>({createRoot:()=>({render:()=>{}})}));
vi.mock('./account-shell',()=>({AccountHeader:()=>null,SiteFooter:()=>null}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();history.replaceState(null,'','#')});

it('preserves an older order page when background refresh happens during pagination',async()=>{
 history.replaceState(null,'','#orders');vi.stubGlobal('scrollTo',vi.fn());
 let finish!:(response:Response)=>void;
 const order={id:'sync-customer-order',status:'delivered',payment_status:'paid',payment_mode:'cash',total_amount:'500',created_at:'2026-10-19T10:00:00+05:00',requested_delivery_at:'2026-10-20T15:00:00+05:00',items:[]};
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
  if(url.endsWith('/auth/csrf'))return new Response(null,{status:204});
  if(url.endsWith('/auth/me'))return new Response(JSON.stringify({user_id:'customer-1',role:'customer',approval_status:'active'}));
  if(url.includes('/orders?')){
   if(url.includes('cursor='))return await new Promise<Response>(resolve=>{finish=resolve});
   return new Response(JSON.stringify({items:[order],next_cursor:'older'}));
  }
  return new Response(JSON.stringify({items:[],next_cursor:null}));
 }));
 render(<App/>);
 fireEvent.click(await screen.findByRole('button',{name:'Показать ещё заказы'}));
 await waitFor(()=>expect(finish).toBeTypeOf('function'));
 await act(async()=>{window.dispatchEvent(new Event('focus'))});
 await act(async()=>{finish(new Response(JSON.stringify({items:[{...order,id:'older-order-1'}],next_cursor:null})))});
 expect(await screen.findByRole('button',{name:/older-or.*Передан/})).toBeTruthy();
});

it('refreshes delivery and payment changes on an already loaded older order page',async()=>{
 history.replaceState(null,'','#orders');vi.stubGlobal('scrollTo',vi.fn());
 let delivered=false;
 const order={id:'newer-order',status:'ready',payment_status:'unpaid',payment_mode:'cash',total_amount:'500',created_at:'2026-10-19T10:00:00+05:00',requested_delivery_at:'2026-10-20T15:00:00+05:00',items:[]};
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
  if(url.endsWith('/auth/csrf'))return new Response(null,{status:204});
  if(url.endsWith('/auth/me'))return new Response(JSON.stringify({user_id:'customer-1',role:'customer',approval_status:'active'}));
  if(url.includes('/orders?'))return new Response(JSON.stringify(url.includes('cursor=')?{items:[{...order,id:'older-order-1',status:delivered?'delivered':'ready',payment_status:delivered?'paid':'unpaid'}],next_cursor:null}:{items:[order],next_cursor:'older'}));
  return new Response(JSON.stringify({items:[],next_cursor:null}));
 }));
 render(<App/>);
 fireEvent.click(await screen.findByRole('button',{name:'Показать ещё заказы'}));
 await screen.findByRole('button',{name:/older-or.*Готов.*Не оплачен/});
 delivered=true;
 await act(async()=>{window.dispatchEvent(new Event('focus'))});
 expect(await screen.findByRole('button',{name:/older-or.*Передан.*Оплачен/})).toBeTruthy();
});
