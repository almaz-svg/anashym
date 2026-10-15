// @vitest-environment jsdom
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { Records } from './workspace';

afterEach(cleanup);

describe('payment record presentation', () => {
    it.each([
        ['pending', 'pending_review', 'Ожидает проверки'],
        ['confirmed', 'confirmed', 'Подтверждён'],
        ['rejected', 'rejected', 'Отклонён'],
    ])('shows one amount and one status for %s payments', (status, state, label) => {
        render(<Records title="Платежи" items={[{
            id: 'payment-1', method: 'kaspi', amount: '123.25', amount_amount: '123.25',
            status, state, unallocated_amount: '123.25',
        }]}/>);
        expect(screen.getAllByText('Сумма')).toHaveLength(1);
        expect(screen.getAllByText(label)).toHaveLength(1);
        // Equal values with a different financial meaning must remain visible.
        expect(screen.getByText('Нераспределённый аванс')).toBeTruthy();
    });

    it('retains amount and state when only compatibility fields are supplied', () => {
        render(<Records title="Платежи" items={[{amount: null, amount_amount: '123.25', status: null, state: 'pending_review'}]}/>);
        expect(screen.getAllByText('Сумма')).toHaveLength(1);
        expect(screen.getByText('Ожидает проверки')).toBeTruthy();
    });

    it('preserves distinct state information and handles a zero amount', () => {
        render(<Records title="Операции" items={[{amount: 0, amount_amount: '0.00', status: 'pending', state: 'confirmed'}]}/>);
        expect(screen.getAllByText('Сумма')).toHaveLength(1);
        expect(screen.getByText('Ожидает проверки')).toBeTruthy();
        expect(screen.getByText('Подтверждён')).toBeTruthy();
    });
});
