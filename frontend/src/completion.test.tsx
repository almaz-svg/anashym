// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { FieldsForm } from './workspace';
import { StaffWorkspace } from './staff';
import { ApiError } from './api';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
beforeEach(()=>{vi.stubGlobal('scrollTo',vi.fn())});
describe('independent access and inline validation', () => {
 it('submits the explicit deferred approval checkbox as a boolean', async () => {
  const submit = vi.fn(async () => ({}));
  render(<FieldsForm title="Доступ клиента" fields={[{name:'deferred_approved',label:'Разрешить отсрочку',type:'checkbox'}]} onSubmit={submit}/>);
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'Сохранить'}));
  await waitFor(() => expect(submit).toHaveBeenCalledWith({deferred_approved:true}));
 });
 it('associates server validation with its field and keeps entered values', async () => {
  render(<FieldsForm title="Возврат" fields={[{name:'reason',label:'Причина'}]} onSubmit={async()=>{throw new ApiError(400,'VALIDATION','Проверьте данные',{reason:['Укажите основание']});}}/>);
  const field=screen.getByLabelText('Причина'); fireEvent.change(field,{target:{value:'ошибка'}});fireEvent.click(screen.getByRole('button',{name:'Сохранить'}));
  await waitFor(()=>expect(field.getAttribute('aria-invalid')).toBe('true'));
  expect((field as HTMLInputElement).value).toBe('ошибка');
  expect(document.getElementById(field.getAttribute('aria-describedby')! )?.textContent).toContain('Укажите основание');
 });
});
describe('role workspaces',()=>{
 const response=()=>new Response(JSON.stringify({items:[],next_cursor:null}));
 it.each(['cashier','accountant'])('offers read-only orders and catalog for %s',async role=>{
  vi.stubGlobal('fetch',vi.fn(async()=>response()));
  render(<StaffWorkspace user={{role,name:'Сотрудник'}} logout={()=>{}}/>);
  expect(screen.getByRole('link',{name:'Заказы'})).toBeTruthy();
  fireEvent.click(screen.getByRole('link',{name:'Каталог'}));
  await waitFor(()=>expect(screen.getByRole('heading',{level:1,name:'Каталог'})).toBeTruthy());
  expect(screen.queryByRole('heading',{name:'Новый товар'})).toBeNull();
 });
 it('refreshes an active child resource when the page refresh button is pressed',async()=>{
  const fetcher=vi.fn(async(_url:any)=>response());vi.stubGlobal('fetch',fetcher);
  render(<StaffWorkspace user={{role:'cashier',name:'Кассир'}} logout={()=>{}}/>);
  await waitFor(()=>expect(fetcher.mock.calls.some(call=>String(call[0]).includes('/payments'))).toBe(true));
  const before=fetcher.mock.calls.filter(call=>String(call[0]).includes('/payments')).length;
  fireEvent.click(screen.getByRole('button',{name:'Обновить'}));
  await waitFor(()=>expect(fetcher.mock.calls.filter(call=>String(call[0]).includes('/payments')).length).toBeGreaterThan(before));
 });
});
