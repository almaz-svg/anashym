// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StaffWorkspace } from './staff';
import { setLanguage } from './preferences';

vi.mock('./account-shell', () => ({ AccountHeader: () => null, SiteFooter: () => null }));
const client = { id: 'client-1', name: 'Кофейня Утро', approval_status: 'pending', debt_amount: '12500', period_days: 14, credit_limit: '0', deferred_approved: false };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); setLanguage('ru'); });
function setup(role='admin') {
    vi.stubGlobal('scrollTo', vi.fn());
    const fetcher = vi.fn(async (url: string, options?: RequestInit) => ({
        ok: true, status: 200,
        json: async () => options?.method === 'POST' ? {} : {items: url.includes('/clients') ? [client] : url.endsWith('/products') ? [{id:'product-1',name:'Пирожное',price_amount:'800',available_qty:6,preparation_minutes:10}] : []},
    }));
    vi.stubGlobal('fetch', fetcher);
    render(<StaffWorkspace user={{role, name:'Администратор'}} logout={()=>{}}/>);
    fireEvent.click(screen.getByRole('link', {name:'Клиенты'}));
    return fetcher;
}
describe('simple client administration', () => {
    it('shows immediate access without obsolete credit approval controls', async () => {
        setup();
        await screen.findAllByRole('heading', {name:'Кофейня Утро'});
        expect(screen.getByText('Доступ открыт')).toBeTruthy();
        expect(screen.getAllByText('Долг').length).toBeGreaterThan(0);
        const settings = screen.getByText('Настройки клиента').closest('details');
        expect(settings?.open).toBe(false);
        settings!.open = true;
        expect(screen.queryByRole('button', {name:'Одобрить доступ'})).toBeNull();
        expect(screen.queryByLabelText('Разрешить отсрочку')).toBeNull();
        expect(screen.queryByLabelText('Лимит KZT')).toBeNull();
    });
    it('changes only the photo when selecting an image', async () => {
        const fetcher = setup();
        fireEvent.click(screen.getByRole('link',{name:'Каталог и склад'}));
        const edit = await screen.findByText('Изменить товар');
        edit.closest('details')!.open = true;
        fireEvent.click(screen.getByRole('button',{name:'Фото 1'}));
        await waitFor(()=>expect(fetcher.mock.calls.some(([url,options])=>url==='/api/v1/products/product-1' && options?.method==='POST')).toBe(true));
        const mutation=fetcher.mock.calls.find(([url,options])=>url==='/api/v1/products/product-1' && options?.method==='POST');
        expect(JSON.parse(String(mutation?.[1]?.body))).toEqual({image_url:new URL('/product-photos/photo-01.jpg',window.location.origin).href});
    });
    it('keeps accountant access read only', async () => {
        setup('accountant');
        await screen.findAllByRole('heading', {name:'Кофейня Утро'});
        expect(screen.queryByRole('button',{name:'Одобрить доступ'})).toBeNull();
        expect(screen.queryByText('Настройки клиента')).toBeNull();
    });
});
