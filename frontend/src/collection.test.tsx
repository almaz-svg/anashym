// @vitest-environment jsdom
import {afterEach,describe,it,expect,vi} from 'vitest';
import {act,renderHook,waitFor,render,screen,fireEvent,cleanup} from '@testing-library/react';
import {useCollection,FieldsForm} from './workspace';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe('cursor collection',()=>{
 it('refreshes all visible pages and removes assignments that left a filtered queue',async()=>{
  let changed=false;
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url.includes('cursor=')?{items:changed?[{id:'second',status:'out_for_delivery'}]:[{id:'second',status:'ready'},{id:'reassigned',status:'ready'}],next_cursor:null}:{items:[{id:'first',status:changed?'out_for_delivery':'ready'}],next_cursor:'page-two'}))));
  const {result}=renderHook(()=>useCollection('/orders?history=active',0,5000));
  await waitFor(()=>expect(result.current.items).toHaveLength(1));
  await act(async()=>{await result.current.loadMore()});expect(result.current.items).toHaveLength(3);
  changed=true;await act(async()=>{window.dispatchEvent(new Event('focus'))});
  await waitFor(()=>expect(result.current.items.map(x=>x.id)).toEqual(['first','second']));
  expect(result.current.items.every(x=>x.status==='out_for_delivery')).toBe(true);
 });
 it('keeps older pages and their cursor while refreshing new registrations',async()=>{
  let fresh=false;
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url.includes('cursor=')?{items:[{id:'older'}],next_cursor:'page-three'}:{items:fresh?[{id:'new-pending'},{id:'existing'}]:[{id:'existing'}],next_cursor:'page-two'}))));
  vi.useFakeTimers();
  try {
   const {result}=renderHook(()=>useCollection('/clients',0,10000));
   await act(async()=>{await vi.advanceTimersByTimeAsync(0)});
   await act(async()=>{await result.current.loadMore()});
   fresh=true;
   await act(async()=>{await vi.advanceTimersByTimeAsync(10000)});
   expect(result.current.items.map(x=>x.id)).toEqual(['new-pending','existing','older']);
   expect(result.current.nextCursor).toBe('page-three');
  } finally {cleanup();vi.useRealTimers()}
 });
 it('refreshes an open client queue and stops polling when unmounted',async()=>{
  let clients=[{id:'existing'}];
  vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({items:clients,next_cursor:null}))));
  vi.useFakeTimers();
  try {
   const {result,unmount}=renderHook(()=>useCollection('/clients',0,10000));
   await act(async()=>{await vi.advanceTimersByTimeAsync(0)});
   expect(result.current.items).toEqual([{id:'existing'}]);
   clients=[{id:'new-pending'},{id:'existing'}];
   await act(async()=>{await vi.advanceTimersByTimeAsync(10000)});
   expect(result.current.items.map(x=>x.id)).toEqual(['new-pending','existing']);
   unmount();clients=[{id:'after-unmount'}];
   await act(async()=>{await vi.advanceTimersByTimeAsync(20000)});
   expect(vi.getTimerCount()).toBe(0);
  } finally {vi.useRealTimers()}
 });
 it('keeps page one on a page-two error, retries its cursor and resets on revision',async()=>{
  const urls:string[]=[];let failed=false;
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>{urls.push(url);if(url.includes('cursor=')){if(!failed){failed=true;return new Response(JSON.stringify({message:'Temporary gateway failure'}),{status:502})}return new Response(JSON.stringify({items:[{id:'old-order'}],next_cursor:null}))}return new Response(JSON.stringify({items:[{id:'new-order'}],next_cursor:'opaque + cursor'}))}));
  const {result,rerender}=renderHook(({revision})=>useCollection('/orders?limit=1',revision),{initialProps:{revision:0}});
  await waitFor(()=>expect(result.current.loading).toBe(false));expect(result.current.items).toEqual([{id:'new-order'}]);
  await act(async()=>{await result.current.loadMore()});expect(result.current.error).toBeTruthy();expect(result.current.items).toHaveLength(1);expect(result.current.nextCursor).toBe('opaque + cursor');
  await act(async()=>{await result.current.loadMore()});expect(result.current.items.map(x=>x.id)).toEqual(['new-order','old-order']);expect(result.current.nextCursor).toBeNull();expect(urls[1]).toBe(urls[2]);expect(urls[1]).toContain('cursor=opaque%20%2B%20cursor');
  rerender({revision:1});await waitFor(()=>expect(result.current.loading).toBe(false));expect(result.current.items).toEqual([{id:'new-order'}]);expect(urls).toHaveLength(4);
 });
 it('ignores an old page response after changing the scoped path',async()=>{
  let resolvePage!:(r:Response)=>void;
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.includes('cursor=')?await new Promise<Response>(resolve=>{resolvePage=resolve}):new Response(JSON.stringify({items:[{id:url.includes('client=b')?'b':'a'}],next_cursor:'next'}))));
  const {result,rerender}=renderHook(({path})=>useCollection(path),{initialProps:{path:'/orders?client=a'}});await waitFor(()=>expect(result.current.loading).toBe(false));
  let pending:Promise<void>;act(()=>{pending=result.current.loadMore()});rerender({path:'/orders?client=b'});await waitFor(()=>expect(result.current.items[0]?.id).toBe('b'));
  await act(async()=>{resolvePage(new Response(JSON.stringify({items:[{id:'foreign-stale'}],next_cursor:null})));await pending!});expect(result.current.items).toEqual([{id:'b'}]);
 });
});

describe('order choice pagination',()=>{it('loads and submits an older order from the next server page',async()=>{vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url.includes('cursor=')?{items:[{id:'older-order-uuid',status:'delivered',total_amount:'100'}],next_cursor:null}:{items:[{id:'newer-order-uuid',status:'submitted',total_amount:'50'}],next_cursor:'older'}))));const submit=vi.fn(async()=>({}));render(<FieldsForm title="Оплата" fields={[{name:'order_id',label:'Заказ'}]} onSubmit={submit}/>);await screen.findByRole('button',{name:'Показать ещё заказы для выбора'});fireEvent.click(screen.getByRole('button',{name:'Показать ещё заказы для выбора'}));await waitFor(()=>expect(screen.getAllByRole('option')).toHaveLength(3));fireEvent.change(screen.getByRole('combobox'),{target:{value:'older-order-uuid'}});fireEvent.click(screen.getByRole('button',{name:'Сохранить'}));await waitFor(()=>expect(submit).toHaveBeenCalledWith({order_id:'older-order-uuid'}));})});
