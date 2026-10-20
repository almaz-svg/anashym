// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {DeliveryPoints} from './customer';

afterEach(()=>{cleanup();vi.unstubAllGlobals()});

it.each([['20:00','09:00'],['12:00','12:00'],['','08:00'],['21:00','']])('blocks an unusable window %s–%s before sending it and preserves the form',async(start,end)=>{
 let posts=0;
 vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
  if(options?.method==='POST'){posts++;return new Response(JSON.stringify({id:'unexpected-point'}),{status:201});}
  return new Response(JSON.stringify({items:[],next_cursor:null}));
 }));
 render(<DeliveryPoints/>);
 fireEvent.change(screen.getByLabelText('Адрес'),{target:{value:'Абая 25'}});
 fireEvent.change(screen.getByLabelText('Получатель'),{target:{value:'Получатель'}});
 fireEvent.change(screen.getByLabelText('Телефон'),{target:{value:'+77019999881'}});
 const startInput=screen.getByLabelText('Доставка с'),endInput=screen.getByLabelText('Доставка до');
 fireEvent.change(startInput,{target:{value:start}});
 fireEvent.change(endInput,{target:{value:end}});
 fireEvent.click(screen.getByRole('button',{name:/^Сохранить$/}));
 await screen.findByRole('alert');
 expect(startInput.getAttribute('aria-invalid')).toBe('true');
 expect(endInput.getAttribute('aria-invalid')).toBe('true');
 expect(screen.getByLabelText('Адрес')).toHaveProperty('value','Абая 25');
 expect(posts).toBe(0);
 fireEvent.change(startInput,{target:{value:'09:00'}});
 fireEvent.change(endInput,{target:{value:'20:00'}});
 fireEvent.click(screen.getByRole('button',{name:/^Сохранить$/}));
 await screen.findByRole('status');
 expect(posts).toBe(1);
});

it('returns the saved address to checkout only after the server accepts it',async()=>{
 const saved={id:'new-point',address:'Алматы, Абая 25',recipient:'Нурислам',phone:'+77019999881'};
 let reject=true;
 vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
  if(options?.method==='POST'){
   expect(JSON.parse(String(options.body))).toMatchObject({address:saved.address,recipient:saved.recipient,phone:saved.phone});
   return new Response(JSON.stringify(reject?{message:'Проверьте адрес'}:saved),{status:reject?422:201});
  }
  return new Response(JSON.stringify({items:[],next_cursor:null}));
 }));
 const created=vi.fn();
 render(<DeliveryPoints onCreated={created}/>);
 fireEvent.change(screen.getByLabelText('Адрес'),{target:{value:saved.address}});
 fireEvent.change(screen.getByLabelText('Получатель'),{target:{value:saved.recipient}});
 fireEvent.change(screen.getByLabelText('Телефон'),{target:{value:saved.phone}});
 fireEvent.click(screen.getByRole('button',{name:'Сохранить и вернуться к заказу'}));
 await screen.findAllByRole('alert');
 expect(created).not.toHaveBeenCalled();
 expect((screen.getByLabelText('Адрес') as HTMLInputElement).value).toBe(saved.address);
 reject=false;
 fireEvent.click(screen.getByRole('button',{name:'Сохранить и вернуться к заказу'}));
 await waitFor(()=>expect(created).toHaveBeenCalledWith(saved));
});

it('confirms server saving and reloads the saved address after remount',async()=>{
 const saved={id:'saved-point',address:'Абая 58',recipient:'aza',phone:'+77075165214'};
 let stored=false;
 vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
  if(options?.method==='POST'){stored=true;return new Response(JSON.stringify(saved),{status:201})}
  return new Response(JSON.stringify({items:stored?[saved]:[],next_cursor:null}));
 }));
 const view=render(<DeliveryPoints/>);
 fireEvent.change(screen.getByLabelText('Адрес'),{target:{value:saved.address}});
 fireEvent.change(screen.getByLabelText('Получатель'),{target:{value:saved.recipient}});
 fireEvent.change(screen.getByLabelText('Телефон'),{target:{value:'8 707 516 5214'}});
 fireEvent.click(screen.getByRole('button',{name:'Сохранить'}));
 expect(await screen.findByRole('status')).toHaveProperty('textContent','Адрес сохранён. Теперь его можно выбрать при оформлении заказа.');
 view.unmount();
 render(<DeliveryPoints/>);
 expect(await screen.findByText(saved.address,{exact:false})).toBeTruthy();
});
