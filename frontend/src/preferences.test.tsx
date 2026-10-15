// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { PreferencesControls, setLanguage, setTheme, t, usePreferences } from './preferences';
import { translations } from './translations';

function PreferencesFixture() {
    usePreferences();
    return <><PreferencesControls/><label>{t('Телефон')}<input aria-label="draft" defaultValue=""/></label><p>{t('Выйти')}</p></>;
}

afterEach(() => { cleanup(); setLanguage('ru'); setTheme('light'); localStorage.clear(); vi.restoreAllMocks(); });

describe('account preferences', () => {
    it('switches both themes without replacing an unfinished form and persists the choice', () => {
        render(<PreferencesFixture/>);
        fireEvent.change(screen.getByLabelText('draft'), {target: {value: '+77012345678'}});
        fireEvent.click(screen.getByRole('button', {name: 'Тема'}));
        expect(document.documentElement.dataset.theme).toBe('dark');
        expect(document.documentElement.style.colorScheme).toBe('dark');
        expect(localStorage.getItem('bakery.theme')).toBe('dark');
        expect((screen.getByLabelText('draft') as HTMLInputElement).value).toBe('+77012345678');
        fireEvent.click(screen.getByRole('button', {name: 'Тема'}));
        expect(document.documentElement.dataset.theme).toBe('light');
    });

    it('switches all languages, updates the document and preserves unfinished input', () => {
        render(<PreferencesFixture/>);
        const languageSelect = screen.getByLabelText('Язык');
        fireEvent.change(screen.getByLabelText('draft'), {target: {value: 'draft'}});
        for (const language of ['en', 'kk', 'ru']) {
            fireEvent.change(languageSelect, {target: {value: language}});
            expect(document.documentElement.lang).toBe(language);
            expect(localStorage.getItem('bakery.language')).toBe(language);
            expect(screen.getByText(language === 'ru' ? 'Выйти' : translations['Выйти'][language as 'en'|'kk'])).toBeTruthy();
            expect((screen.getByLabelText('draft') as HTMLInputElement).value).toBe('draft');
        }
    });

    it('loads persisted choices on a new application module and falls back for invalid values', async () => {
        localStorage.setItem('bakery.language', 'kk');
        localStorage.setItem('bakery.theme', 'dark');
        vi.resetModules();
        const reloaded = await import('./preferences');
        expect(reloaded.t('Выйти')).toBe(translations['Выйти'].kk);
        expect(document.documentElement.lang).toBe('kk');
        expect(document.documentElement.dataset.theme).toBe('dark');
        localStorage.setItem('bakery.language', 'invalid');
        localStorage.setItem('bakery.theme', 'invalid');
        vi.resetModules();
        const fallback = await import('./preferences');
        expect(fallback.t('Выйти')).toBe('Выйти');
        expect(document.documentElement.dataset.theme).toBe('light');
    });

    it('keeps controls working when browser storage is unavailable', () => {
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {throw new Error('storage disabled');});
        render(<PreferencesFixture/>);
        fireEvent.click(screen.getByRole('button', {name: 'Тема'}));
        fireEvent.change(screen.getByLabelText('Язык'), {target: {value: 'en'}});
        expect(document.documentElement.dataset.theme).toBe('dark');
        expect(document.documentElement.lang).toBe('en');
        expect(screen.getByText(translations['Выйти'].en)).toBeTruthy();
    });
});
