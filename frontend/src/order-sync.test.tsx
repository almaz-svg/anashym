// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {OrderSummary} from './order-summary';
import {StaffWorkspace} from './staff';

vi.mock('./account-shell',()=>({AccountHeader:()=>null,SiteFooter:()=>null}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();history.replaceState(null,'','#')});
const order={id:'order-sync-1',client_name:'Кофейня Утро',status:'ready',payment_mode:'cash',payment_status:'unpaid',total_amount:'1000.00',paid_amount:'0.00',cash_paid_amount:'0.00',kaspi_paid_amount:'0.00',outstanding_amount:'0.00',delivered_total_amount:'0.00',courier_name:'Алия',courier_id:'courier-1',version:1,requested_delivery_at:'2026-10-20T15:00:00+05:00',address_snapshot:{address:'Абая 25',recipient:'Алмаз',phone:'+77019999999'},items:[{product_id:'cake-1',name:'Медовик',quantity:2,delivered_quantity:0,line_total_amount:'1000.00'}]};

it('shows destination, courier, actual paid methods and remaining debt together',()=>{
 render(<OrderSummary order={{...order,status:'delivered',payment_mode:'deferred',paid_amount:'700',cash_paid_amount:'500',kaspi_paid_amount:'200',outstanding_amount:'300',delivered_total_amount:'1000'}}/>);
 expect(screen.getByText('Абая 25')).toBeTruthy();expect(screen.getByText('Алия')).toBeTruthy();
 expect(screen.getByText('Оплачено наличными').parentElement?.textContent?.replace(/\s/g,'')).toContain('500');
 expect(screen.getByText('Оплачено Kaspi').parentElement?.textContent?.replace(/\s/g,'')).toContain('200');
 expect(screen.getByText('Осталось оплатить').parentElement?.textContent?.replace(/\s/g,'')).toContain('300');
});

it('does not claim that an undelivered cash order has been paid or has created debt',()=>{
 render(<OrderSummary order={order}/>);
 expect(screen.getByText('При получении')).toBeTruthy();
 expect(screen.queryByText('Осталось оплатить')).toBeNull();
 expect(screen.queryByText('Оплачено наличными')).toBeNull();
});

it('lets an assigned courier accept the delivery and keeps payment status visible in the queue',async()=>{
 let state={...order};
 vi.stubGlobal('scrollTo',vi.fn());
 vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
  if(options?.method==='POST'){
   expect(url).toBe('/api/v1/orders/order-sync-1/transition');
   expect(JSON.parse(String(options.body))).toEqual({status:'out_for_delivery',version:1});
   state={...state,status:'out_for_delivery',version:2};return new Response(JSON.stringify(state));
  }
  return new Response(JSON.stringify(url==='/api/v1/orders/order-sync-1'?state:{items:url.includes('/orders')?[state]:[],next_cursor:null}));
 }));
 render(<StaffWorkspace user={{role:'courier',name:'Алия'}} logout={()=>{}}/>);
 const row=await screen.findByRole('button',{name:/order-sy/});
 expect(row.textContent).toContain('Наличные');expect(row.textContent).toContain('Медовик');
 fireEvent.click(row);fireEvent.click(await screen.findByRole('button',{name:'Принять доставку'}));
 await waitFor(()=>expect(screen.getByRole('heading',{name:'Завершить доставку'})).toBeTruthy());
 expect(screen.queryByRole('button',{name:'Принять доставку'})).toBeNull();
 expect(screen.getByRole('button',{name:'Выполненные'})).toBeTruthy();
});

it('refreshes an open delivery without clearing entered cash or uploaded proof',async()=>{
 let state={...order,status:'out_for_delivery'};
 vi.stubGlobal('scrollTo',vi.fn());
 vi.stubGlobal('URL',class extends URL{static createObjectURL(){return 'blob:delivery-proof'}static revokeObjectURL(){}});
 vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
  if(url==='/api/v1/files'&&options?.method==='POST')return new Response(JSON.stringify({items:[{id:'proof-1'}]}));
  if(url==='/api/v1/files/proof-1')return new Response(JSON.stringify({url:'/proof-bytes'}));
  if(url==='/proof-bytes')return new Response('proof');
  return new Response(JSON.stringify(url==='/api/v1/orders/order-sync-1'?state:{items:url.includes('/orders')?[state]:[],next_cursor:null}));
 }));
 render(<StaffWorkspace user={{role:'courier',name:'Алия'}} logout={()=>{}}/>);
 fireEvent.click(await screen.findByRole('button',{name:/order-sy/}));
 const cash=await screen.findByLabelText('Получено наличными, KZT');
 fireEvent.change(cash,{target:{value:'1000'}});
 const upload=document.querySelector('input[type="file"]')!;
 fireEvent.change(upload,{target:{files:[new File(['proof'],'delivery.png',{type:'image/png'})]}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Подтвердить доставку'})).toHaveProperty('disabled',false));
 state={...state,courier_name:'Алия обновлена',version:2};
 await act(async()=>{window.dispatchEvent(new Event('focus'))});
 await screen.findByText('Алия обновлена',{exact:true});
 expect(cash).toHaveProperty('value','1000');
 expect(screen.getByRole('button',{name:'Подтвердить доставку'})).toHaveProperty('disabled',false);
});

it('shows actual cash and Kaspi settlement directly on the cashier home screen',async()=>{
 history.replaceState(null,'','#payments');vi.stubGlobal('scrollTo',vi.fn());
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify({items:url.includes('/orders')?[{...order,status:'delivered',payment_mode:'deferred',payment_status:'partial',cash_paid_amount:'500',kaspi_paid_amount:'200',outstanding_amount:'300',delivered_total_amount:'1000'}]:[],next_cursor:null}))));
 render(<StaffWorkspace user={{role:'cashier'}} logout={()=>{}}/>);
 const row=await screen.findByRole('button',{name:/order-sy/});
 expect(row.textContent).toContain('Наличные:');expect(row.textContent).toContain('Kaspi:');expect(row.textContent).toContain('Осталось оплатить');
});

it('does not restore an old delivery state when an initial detail request arrives after a newer refresh',async()=>{
 let state={...order},first=true,finish!:(response:Response)=>void;
 vi.stubGlobal('scrollTo',vi.fn());
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
  if(url==='/api/v1/orders/order-sync-1'){
   if(first){first=false;return await new Promise<Response>(resolve=>{finish=resolve})}
   return new Response(JSON.stringify(state));
  }
  return new Response(JSON.stringify({items:url.includes('/orders')?[state]:[],next_cursor:null}));
 }));
 render(<StaffWorkspace user={{role:'courier'}} logout={()=>{}}/>);
 fireEvent.click(await screen.findByRole('button',{name:/order-sy/}));
 state={...state,status:'out_for_delivery',version:2};
 await act(async()=>{window.dispatchEvent(new Event('focus'))});
 await screen.findByRole('heading',{name:'Завершить доставку'});
 await act(async()=>{finish(new Response(JSON.stringify(order)))});
 expect(screen.getByRole('heading',{name:'Завершить доставку'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Принять доставку'})).toBeNull();
});

it('closes an open assignment after it is reassigned to another courier',async()=>{
 let reassigned=false;vi.stubGlobal('scrollTo',vi.fn());
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
  if(url==='/api/v1/orders/order-sync-1')return new Response(JSON.stringify(reassigned?{code:'NOT_FOUND',message:'Заказ не найден'}:order),{status:reassigned?404:200});
  return new Response(JSON.stringify({items:url.includes('/orders')&&!reassigned?[order]:[],next_cursor:null}));
 }));
 render(<StaffWorkspace user={{role:'courier'}} logout={()=>{}}/>);
 fireEvent.click(await screen.findByRole('button',{name:/order-sy/}));
 await screen.findByRole('button',{name:'Принять доставку'});
 reassigned=true;await act(async()=>{window.dispatchEvent(new Event('focus'))});
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Принять доставку'})).toBeNull());
 expect(screen.queryByRole('heading',{name:'Заказ №order-sy'})).toBeNull();
});
