// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AIOrder } from './ai-order';
import { apiRequest } from './api';
import { ApiError } from './api';

const testCatalog = vi.hoisted(() => ({price:'1500.00', calls:vi.fn()}));

vi.mock('./api', async () => ({ ...await vi.importActual('./api'), apiRequest: vi.fn() }));
vi.mock('./workspace', async () => ({ ...await vi.importActual('./workspace'), useCollection: (path: string, revision = 0) => {testCatalog.calls(path, revision); return ({
 items: path.startsWith('/clients') ? [{id:'client',name:'Кофейня',approval_status:'active'}] : path.startsWith('/delivery-points') ? [{id:'address',client_id:'client',address:'Адрес'}] : path.startsWith('/catalog') ? [{id:'cake',name:'Медовик',price_amount:testCatalog.price,active:true}] : [],
 loading:false,error:null,nextCursor:null,loadMore:vi.fn(),
});} }));
let op: any;
beforeEach(() => { vi.clearAllMocks(); testCatalog.price='1500.00'; op = {busy:false,act:vi.fn(async()=>({id:'order'})),setError:vi.fn()}; vi.mocked(apiRequest).mockResolvedValue({enabled:false,reason:'AI_NOT_CONFIGURED'}); });
afterEach(cleanup);
function open() { render(<AIOrder op={op}/>); fireEvent.click(screen.getByRole('button',{name:'Создать заказ из сообщения'})); }
function message() { return screen.getByLabelText('Сообщение клиента') as HTMLTextAreaElement; }
function fill() {
 fireEvent.change(screen.getByLabelText('Клиент'),{target:{value:'client'}});
 fireEvent.change(screen.getByLabelText('Адрес доставки'),{target:{value:'address'}});
 fireEvent.change(screen.getByLabelText('Дата доставки'),{target:{value:new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Almaty'})}});
 fireEvent.change(screen.getByLabelText('Время доставки'),{target:{value:'12:00'}});
 fireEvent.change(screen.getByLabelText('Способ оплаты'),{target:{value:'cash'}});
 fireEvent.click(screen.getByRole('button',{name:'Добавить позицию'}));
 fireEvent.change(screen.getByLabelText('Товар 1'),{target:{value:'cake'}});
 fireEvent.change(screen.getByLabelText('Количество 1'),{target:{value:'2'}});
 fireEvent.click(screen.getByLabelText('Проверил товары, количество, дату, адрес и условия оплаты'));
}
it('shows disabled AI honestly and clears source on close/reopen without storage',async()=>{
 const store=vi.spyOn(Storage.prototype,'setItem'); open();
 await screen.findByText('ИИ пока не подключён. Заполните черновик вручную.');
 fireEvent.change(message(),{target:{value:'PRIVATE_MESSAGE'}});
 expect((screen.getByRole('button',{name:'Разобрать сообщение'}) as HTMLButtonElement).disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Закрыть черновик'}));
 fireEvent.click(screen.getByRole('button',{name:'Создать заказ из сообщения'}));
 expect(message().value).toBe(''); expect(store).not.toHaveBeenCalled(); store.mockRestore();
});
it('manual fallback submits only confirmed fields and clears message after success',async()=>{
 open(); fireEvent.change(message(),{target:{value:'PRIVATE_MESSAGE'}}); fill();
 fireEvent.click(screen.getByRole('button',{name:'Создать заказ'}));
 await waitFor(()=>expect(op.act).toHaveBeenCalledOnce());
 const payload=op.act.mock.calls[0][1]; expect(JSON.stringify(payload)).not.toContain('PRIVATE_MESSAGE');
 expect(payload).toMatchObject({client_id:'client',ai_used:false,items:[{product_id:'cake',quantity:2,expected_unit_price:'1500.00'}]});
 await screen.findByText('Заказ создан.'); expect(screen.queryByLabelText('Сообщение клиента')).toBeNull();
});
it('preserves message and reviewed fields after order error',async()=>{
 op.act.mockRejectedValue(new Error('Недостаточно товара')); open(); fireEvent.change(message(),{target:{value:'PRIVATE_MESSAGE'}});fill();
 fireEvent.click(screen.getByRole('button',{name:'Создать заказ'}));
 await screen.findByText('Недостаточно товара'); expect(message().value).toBe('PRIVATE_MESSAGE');
 expect((screen.getByLabelText('Количество 1') as HTMLInputElement).value).toBe('2');
});
it('parse does not create orders and missing quantities block confirmation',async()=>{
 vi.mocked(apiRequest).mockImplementation(async(path:any)=>path==='/ai/status'?{enabled:true}:{items:[{source_text:'медовик',product_id:'cake',quantity:null,unit:'portion',issues:['Уточните количество']}],delivery_date:null,questions:['На какую дату?']});
 open(); fireEvent.change(screen.getByLabelText('Клиент'),{target:{value:'client'}});fireEvent.change(message(),{target:{value:'медовик'}});
 await waitFor(()=>expect((screen.getByRole('button',{name:'Разобрать сообщение'}) as HTMLButtonElement).disabled).toBe(false));
 fireEvent.click(screen.getByRole('button',{name:'Разобрать сообщение'}));
 await screen.findByText('Уточните количество');expect(op.act).not.toHaveBeenCalled();
 expect((screen.getByLabelText('Количество 1') as HTMLInputElement).value).toBe('');
 expect((screen.getByRole('button',{name:'Создать заказ'}) as HTMLButtonElement).disabled).toBe(true);
});
it('refreshes changed prices while keeping source and requires new approval',async()=>{
 op.act.mockImplementationOnce(async()=>{testCatalog.price='1600.00'; throw new ApiError(409,'PRICE_CHANGED','Цена товара изменилась');});
 open(); fireEvent.change(message(),{target:{value:'PRIVATE_MESSAGE'}});fill();
 fireEvent.click(screen.getByRole('button',{name:'Создать заказ'}));
 await screen.findByText('Цена товара изменилась');
 await waitFor(()=>expect(testCatalog.calls.mock.calls.some(([path,revision])=>path.startsWith('/catalog')&&revision===1)).toBe(true));
 expect(message().value).toBe('PRIVATE_MESSAGE');
 expect((screen.getByLabelText('Проверил товары, количество, дату, адрес и условия оплаты') as HTMLInputElement).checked).toBe(false);
 fireEvent.click(screen.getByLabelText('Проверил товары, количество, дату, адрес и условия оплаты'));
 fireEvent.click(screen.getByRole('button',{name:'Создать заказ'}));
 await screen.findByText('Заказ создан.');
 expect(op.act.mock.calls[1][1].items[0].expected_unit_price).toBe('1600.00');
});
it('ignores a parse response arriving after the form was closed',async()=>{
 let resolve!: (value:any)=>void;
 vi.mocked(apiRequest).mockImplementation(async(path:any)=>path==='/ai/status'?{enabled:true}:new Promise(done=>{resolve=done}));
 open(); fireEvent.change(screen.getByLabelText('Клиент'),{target:{value:'client'}});fireEvent.change(message(),{target:{value:'медовик'}});
 await waitFor(()=>expect((screen.getByRole('button',{name:'Разобрать сообщение'}) as HTMLButtonElement).disabled).toBe(false));
 fireEvent.click(screen.getByRole('button',{name:'Разобрать сообщение'}));
 fireEvent.click(screen.getByRole('button',{name:'Закрыть черновик'}));
 fireEvent.click(screen.getByRole('button',{name:'Создать заказ из сообщения'}));
 await act(async()=>{resolve({items:[{source_text:'медовик',product_id:'cake',quantity:'2',unit:'portion',issues:[]}],delivery_date:null,questions:[]})});
 expect(message().value).toBe('');expect(screen.queryByLabelText('Товар 1')).toBeNull();expect(op.act).not.toHaveBeenCalled();
});
