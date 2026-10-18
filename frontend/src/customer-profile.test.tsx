// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Payments } from './customer';
import { CustomerProfile } from './customer-profile';
import { AccountHeader } from './account-shell';

function ProfileScreen({onLogout}: {onLogout: () => void}) {
    return <><AccountHeader user={{name: 'Тестовый покупатель'}} logout={onLogout}/><CustomerProfile/></>;
}
import { FieldsForm, WorkspaceRevision } from './workspace';
import { setLanguage, usePreferences } from './preferences';

const profileResponse = {
    profile: {
        name: 'Кофейня Утро', contact_name: 'Алия', phone: '+77010000001',
        category: 'coffee_shop', category_other: '', description: 'Кофе и завтраки',
        approval_status: 'active', preferred_payment_mode: 'deferred',
        expected_order_quantity: 25, expected_order_frequency: 'weekly',
        period_days: 14, credit_limit_amount: '100000.00',
    },
    from: '2026-10-12', to: '2026-10-18', generated_at: '2026-10-14T08:00:00Z', currency: 'KZT',
    balance: { debt_amount: '12500.00', advance_amount: '0.00', overdue_amount: '2500.00', unconfirmed_payment_amount: '4000.00' },
    period: { delivered_amount: '20000.00', return_credit_amount: '1000.00', turnover_amount: '19000.00', paid_amount: '7500.00', refund_amount: '0.00', outstanding_amount: '11500.00' },
};

afterEach(() => { cleanup(); setLanguage('ru'); vi.unstubAllGlobals(); });

describe('customer payment summary', () => {
    it('shows full debt independently of unconfirmed payments above the form', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/profile') ? profileResponse : { items: [] }))));
        render(<Payments />);
        const debt = await screen.findByRole('article', { name: 'Общая задолженность' });
        expect(debt.textContent?.replace(/\s/g, '')).toContain('12500');
        expect(debt.querySelector('strong')?.classList.contains('positive')).toBe(true);
        expect(screen.getByRole('article', { name: 'Ожидает подтверждения' }).textContent?.replace(/\s/g, '')).toContain('4000');
        expect(screen.getByRole('article', { name: 'Подтверждённые оплаты за неделю' }).textContent?.replace(/\s/g, '')).toContain('7500');
        const formHeading = screen.getByRole('heading', { name: 'Оплата продавцу через Kaspi' });
        expect(debt.compareDocumentPosition(formHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        expect(screen.getByText(/12\.10\.2026.*18\.10\.2026/)).toBeTruthy();
    });

    it('shows a failed summary as unavailable and retries without displaying invented zero balances', async () => {
        let failed = true;
        vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/profile')
            ? new Response(JSON.stringify(failed ? { message: 'Сводка временно недоступна' } : profileResponse), { status: failed ? 503 : 200 })
            : new Response(JSON.stringify({ items: [] }))));
        render(<Payments />);
        expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Сводка временно недоступна');
        expect(screen.queryByRole('article', { name: 'Общая задолженность' })).toBeNull();
        failed = false;
        fireEvent.click(screen.getByRole('button', { name: 'Повторить загрузку сводки' }));
        expect(await screen.findByRole('article', { name: 'Общая задолженность' })).toBeTruthy();
    });

    it('refreshes the unconfirmed amount after submitting a payment while debt remains unchanged', async () => {
        let reported = false;
        vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:()=> 'blob:test-proof',revokeObjectURL:()=>{}}));
        vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
            if (url.endsWith('/payments') && options?.method === 'POST') {
                expect(JSON.parse(String(options.body))).toMatchObject({order_id:'order-1',proof_id:'proof-1',amount:'1000'});
                reported = true;
                return new Response(JSON.stringify({ id: 'reported-payment' }));
            }
            if(url.includes('/orders?'))return new Response(JSON.stringify({items:[{id:'order-1',status:'delivered',total_amount:'12500'}]}));
            if(url.endsWith('/files')&&options?.method==='POST')return new Response(JSON.stringify({items:[{id:'proof-1'}]}));
            if(url.endsWith('/files/proof-1'))return new Response(JSON.stringify({url:'/signed-proof'}));
            if(url==='/signed-proof')return new Response(new Blob(['image']));
            return new Response(JSON.stringify(url.endsWith('/profile') ? {
                ...profileResponse,
                balance: { ...profileResponse.balance, unconfirmed_payment_amount: reported ? '5000.00' : '4000.00' },
            } : { items: [] }));
        }));
        render(<Payments />);
        await screen.findByRole('article', { name: 'Ожидает подтверждения' });
        fireEvent.change(screen.getByLabelText('Сумма, KZT'), { target: { value: '1000' } });
        fireEvent.change(screen.getByLabelText('Номер перевода / комментарий'), { target: { value: 'Перевод' } });
        fireEvent.change(screen.getByLabelText('Заказ'), {target:{value:'order-1'}});
        fireEvent.change(screen.getByLabelText('Обязательное фото подтверждения'), {target:{files:[new File(['image'],'receipt.png',{type:'image/png'})]}});
        await waitFor(()=>expect(screen.getByRole('button',{name:'Отправить на проверку'})).toHaveProperty('disabled',false));
        fireEvent.click(screen.getByRole('button', { name: 'Отправить на проверку' }));
        await waitFor(() => expect(screen.getByRole('article', { name: 'Ожидает подтверждения' }).textContent?.replace(/\s/g, '')).toContain('5000'));
        expect(screen.getByRole('article', { name: 'Общая задолженность' }).textContent?.replace(/\s/g, '')).toContain('12500');
    });
});

describe('customer profile', () => {
    it('shows readable account details and offers working logout and finance links', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(profileResponse))));
        const logout = vi.fn();
        render(<ProfileScreen onLogout={logout}/>);
        expect(await screen.findByRole('heading', { name: 'Кофейня Утро' })).toBeTruthy();
        expect(screen.getByText('+77010000001')).toBeTruthy();
        expect(screen.getByText('Раз в неделю')).toBeTruthy();
        expect(screen.getByRole('link', { name: 'Перейти к оплатам' }).getAttribute('href')).toBe('#payments');
        expect(screen.getByRole('link', { name: 'Подробнее о задолженности' }).getAttribute('href')).toBe('#debt');
        expect(screen.queryByText('contact_name')).toBeNull();
        fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
        expect(logout).toHaveBeenCalledOnce();
    });

    it('applies complete dates together and displays the server outstanding amount for that period', async () => {
        const urls: string[] = [];
        vi.stubGlobal('fetch', vi.fn(async (url: string) => {
            if(url.includes('/profile'))urls.push(url);
            return new Response(JSON.stringify(url.endsWith('/profile?from=2026-09-01&to=2026-09-30') ? {
                ...profileResponse, from: '2026-09-01', to: '2026-09-30',
                period: { ...profileResponse.period, delivered_amount: '24000.00', paid_amount: '9000.00', outstanding_amount: '3200.00' },
            } : profileResponse));
        }));
        render(<ProfileScreen onLogout={() => {}}/>);
        await screen.findByRole('article', { name: 'Передано за период' });
        fireEvent.change(screen.getByLabelText('Начало периода'), { target: { value: '2026-09-01' } });
        fireEvent.change(screen.getByLabelText('Конец периода'), { target: { value: '2026-09-30' } });
        expect(urls).toEqual(['/api/v1/profile']);
        fireEvent.click(screen.getByRole('button', { name: 'Показать период' }));
        await waitFor(() => expect(screen.getByRole('article', { name: 'Осталось оплатить по поставкам периода' }).textContent?.replace(/\s/g, '')).toContain('3200'));
        expect(urls).toEqual(['/api/v1/profile', '/api/v1/profile?from=2026-09-01&to=2026-09-30']);
        expect(screen.getByText('01.09.2026 — 30.09.2026')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Текущая неделя' }));
        await waitFor(() => expect(screen.getByLabelText('Начало периода')).toHaveProperty('value', '2026-10-12'));
        expect(urls.at(-1)).toBe('/api/v1/profile');
    });

    it('keeps zero debt neutral while showing an advance', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
            ...profileResponse,
            balance: { debt_amount: '0.00', advance_amount: '1800.00', overdue_amount: '0.00', unconfirmed_payment_amount: '0.00' },
        }))));
        render(<ProfileScreen onLogout={() => {}}/>);
        const debt = await screen.findByRole('article', { name: 'Общая задолженность' });
        expect(debt.querySelector('strong')?.classList.contains('positive')).toBe(false);
        expect(screen.getByRole('article', { name: 'Аванс' }).textContent?.replace(/\s/g, '')).toContain('1800');
    });

    it('allows logout and retry if profile loading fails without fabricating balances', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ message: 'Профиль временно недоступен' }), { status: 503 })));
        const logout = vi.fn();
        render(<ProfileScreen onLogout={logout}/>);
        expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Профиль временно недоступен');
        expect(screen.queryByRole('article', { name: 'Общая задолженность' })).toBeNull();
        expect(screen.getByRole('button', { name: 'Повторить загрузку профиля' })).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
        expect(logout).toHaveBeenCalledOnce();
    });
});

describe('language changes in account forms', () => {
    it('preserves draft dates when a background account refresh returns the displayed period', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(profileResponse))));
        const view = render(<WorkspaceRevision.Provider value={0}><CustomerProfile/></WorkspaceRevision.Provider>);
        await screen.findByRole('article', { name: 'Передано за период' });
        fireEvent.change(screen.getByLabelText('Начало периода'), { target: { value: '2026-09-01' } });
        view.rerender(<WorkspaceRevision.Provider value={1}><CustomerProfile/></WorkspaceRevision.Provider>);
        await screen.findByRole('article', { name: 'Передано за период' });
        expect(screen.getByLabelText('Начало периода')).toHaveProperty('value', '2026-09-01');
    });

    it('preserves draft profile dates and customer identity when switching the interface language', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ...profileResponse, profile: { ...profileResponse.profile, name: 'Заказы' } }))));
        function Account() { usePreferences(); return <ProfileScreen onLogout={() => {}}/>; }
        render(<Account/>);
        await screen.findByRole('heading', { name: 'Заказы' });
        const from = screen.getByLabelText('Начало периода');
        fireEvent.change(from, { target: { value: '2026-09-01' } });
        act(() => setLanguage('en'));
        expect(screen.getByRole('heading', { name: 'Заказы' })).toBeTruthy();
        expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy();
        expect(from).toHaveProperty('value', '2026-09-01');
        expect(document.querySelector('.debt-value')?.textContent).toContain('12,500');
    });

    it('translates form controls without translating resource names or changing submitted values', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ items: [{ id: 'product-1', name: 'Способ оплаты', active: true }] }))));
        const submit = vi.fn(async () => ({}));
        function AccountForm() {
            usePreferences();
            return <FieldsForm title="Заказы" fields={[{ name: 'product_id', label: 'Название' }, { name: 'method', label: 'Способ оплаты', options: [['cash', 'Наличные'], ['deferred', 'Отсрочка']] }, { name: 'amount', label: 'Сумма', type: 'number' }]} onSubmit={submit}/>;
        }
        render(<AccountForm/>);
        await screen.findByRole('option', { name: 'Способ оплаты' });
        fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'product-1' } });
        fireEvent.change(screen.getByLabelText('Способ оплаты'), { target: { value: 'cash' } });
        fireEvent.change(screen.getByLabelText('Сумма'), { target: { value: '5500' } });
        act(() => setLanguage('en'));
        expect(screen.getByRole('option', { name: 'Способ оплаты' })).toHaveProperty('selected', true);
        expect(screen.getByRole('combobox', { name: 'Payment method' })).toHaveProperty('value', 'cash');
        expect(screen.getByRole('option', { name: 'Cash' })).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));
        await waitFor(() => expect(submit).toHaveBeenCalledWith({ product_id: 'product-1', method: 'cash', amount: 5500 }));
    });
});
