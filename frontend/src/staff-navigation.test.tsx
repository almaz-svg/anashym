// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {StaffWorkspace} from './staff';
vi.mock('./account-shell',()=>({SiteFooter:()=>null,AccountHeader:({onNotifications,onDebt}:any)=><><button onClick={onNotifications}>Header notifications</button><button onClick={onDebt}>Header debt</button></>}));
beforeEach(()=>{history.replaceState(null,'','#');vi.stubGlobal('scrollTo',vi.fn());vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,json:async()=>({items:[]})})));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();history.replaceState(null,'','#');});
const mount=(role='admin')=>render(<StaffWorkspace user={{role,name:'Staff'}} logout={()=>{}}/>);
it('loads a permitted direct route and preserves it on remount',()=>{
 history.replaceState(null,'','#clients');const view=mount();expect(screen.getByRole('heading',{level:1}).textContent).toBe('Клиенты');
 view.unmount();mount();expect(screen.getByRole('heading',{level:1}).textContent).toBe('Клиенты');
});
it('preserves the staff section from the audit on a direct link and remount',()=>{
 history.replaceState(null,'','#staff');const view=mount();expect(screen.getByRole('heading',{level:1}).textContent).toBe('Сотрудники');
 view.unmount();mount();expect(location.hash).toBe('#staff');expect(screen.getByRole('heading',{level:1}).textContent).toBe('Сотрудники');
});
it.each(['#unknown','#staff'])('replaces invalid or forbidden courier route %s with its first allowed route',(hash)=>{
 history.replaceState(null,'',hash);mount('courier');expect(screen.getByRole('heading',{level:1}).textContent).toBe('Задания');expect(location.hash).toBe('#orders');
});
it('writes menu, additional, header notification and debt navigation into URL',()=>{
 mount();fireEvent.click(screen.getByRole('link',{name:'Клиенты'}));expect(location.hash).toBe('#clients');
 fireEvent.click(screen.getByText('Дополнительно'));fireEvent.click(screen.getByRole('link',{name:'Журнал'}));expect(location.hash).toBe('#audit');
 fireEvent.click(screen.getByRole('button',{name:'Header notifications'}));expect(location.hash).toBe('#notifications');expect(screen.getByRole('heading',{level:1}).textContent).toBe('Уведомления');
 fireEvent.click(screen.getByRole('button',{name:'Header debt'}));expect(location.hash).toBe('#clients');
});
it('responds to hash and back/forward history events and role changes',async()=>{
 const view=mount();act(()=>{history.pushState(null,'','#payments');window.dispatchEvent(new HashChangeEvent('hashchange'));});
 await waitFor(()=>expect(screen.getByRole('heading',{level:1}).textContent).toBe('Платежи'));
 act(()=>{history.replaceState(null,'','#clients');window.dispatchEvent(new PopStateEvent('popstate'));});
 expect(screen.getByRole('heading',{level:1}).textContent).toBe('Клиенты');
 view.rerender(<StaffWorkspace user={{role:'courier'}} logout={()=>{}}/>);expect(location.hash).toBe('#orders');expect(screen.getByRole('heading',{level:1}).textContent).toBe('Задания');
});
