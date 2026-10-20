// @vitest-environment jsdom
import {act,cleanup,renderHook} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {useLiveRefresh} from './live-refresh';

afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks()});

it('refreshes visible screens on timer, focus and local mutations, with no overlap',async()=>{
 vi.useFakeTimers();let count=0,finish:(()=>void)|undefined;
 const {unmount}=renderHook(()=>useLiveRefresh(async()=>{count++;await new Promise<void>(resolve=>{finish=resolve})}));
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000)});expect(count).toBe(1);
 act(()=>{window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('bakery:data-changed'))});expect(count).toBe(1);
 await act(async()=>{finish?.()});
 await act(async()=>{window.dispatchEvent(new Event('focus'))});expect(count).toBe(2);
 await act(async()=>{finish?.()});
 await act(async()=>{window.dispatchEvent(new Event('bakery:data-changed'))});expect(count).toBe(3);
 unmount();expect(vi.getTimerCount()).toBe(0);
});

it('does not poll hidden or disabled screens and invalidates pending results on scope changes',async()=>{
 vi.useFakeTimers();let current:(()=>boolean)|undefined,count=0;
 vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden');
 const {rerender,unmount}=renderHook(({enabled,scope})=>useLiveRefresh(live=>{count++;current=live},enabled,5000,scope),{initialProps:{enabled:true,scope:'order-a'}});
 await act(async()=>{await vi.advanceTimersByTimeAsync(10000)});expect(count).toBe(0);
 vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');
 await act(async()=>{document.dispatchEvent(new Event('visibilitychange'))});expect(count).toBe(1);expect(current?.()).toBe(true);
 const old=current;rerender({enabled:true,scope:'order-b'});expect(old?.()).toBe(false);
 rerender({enabled:false,scope:'order-b'});
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000)});expect(count).toBe(1);
 unmount();
});
