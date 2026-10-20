import React, { useSyncExternalStore } from 'react';
import { Sun, Moon, ChevronDown } from 'lucide-react';
import { translations } from './translations';

export type Language = 'ru' | 'kk' | 'en';
export type Theme = 'light' | 'dark';
const eventName = 'bakery:preferences';
function saved(key: string) {
    try { return localStorage.getItem('bakery.' + key); } catch { return null; }
}
let language: Language = (['ru', 'kk', 'en'].includes(saved('language') || '') ? saved('language') : 'ru') as Language;
let theme: Theme = saved('theme') === 'dark' ? 'dark' : 'light';

export function t(source: string, values: Record<string, string | number> = {}) {
    const message = language === 'ru' ? source : translations[source]?.[language] || source;
    return message.replace(/\{\{(\w+)\}\}/g, (match, name) => String(values[name] ?? match));
}
export function locale() { return { ru: 'ru-KZ', kk: 'kk-KZ', en: 'en-GB' }[language]; }
function applyDocument() {
    if (typeof document === 'undefined') return;
    document.documentElement.dataset.theme = theme;
    document.documentElement.lang = language;
    document.documentElement.style.colorScheme = theme;
    document.title = t('Кондитерская — личный кабинет');
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#161719' : '#f7f7f8');
}
function emit() { applyDocument(); if (typeof window !== 'undefined') window.dispatchEvent(new Event(eventName)); }
export function setLanguage(value: Language) {
    if (!['ru', 'kk', 'en'].includes(value)) return;
    language = value;
    try { localStorage.setItem('bakery.language', value); } catch { /* Selection still works for this tab. */ }
    emit();
}
export function setTheme(value: Theme) {
    if (!['light', 'dark'].includes(value)) return;
    theme = value;
    try { localStorage.setItem('bakery.theme', value); } catch { /* Selection still works for this tab. */ }
    emit();
}
function subscribe(callback: () => void) {
    const storage = (event: StorageEvent) => {
        if (event.key !== null && !event.key.startsWith('bakery.')) return;
        language = (['ru', 'kk', 'en'].includes(saved('language') || '') ? saved('language') : 'ru') as Language;
        theme = saved('theme') === 'dark' ? 'dark' : 'light';
        applyDocument(); callback();
    };
    window.addEventListener(eventName, callback);
    window.addEventListener('storage', storage);
    return () => { window.removeEventListener(eventName, callback); window.removeEventListener('storage', storage); };
}
export function usePreferences() {
    useSyncExternalStore(subscribe, () => language + ':' + theme);
    return { language, theme };
}
export function PreferencesControls() {
    const prefs = usePreferences();
    return <div className="preferences-controls">
        <button type="button" className="theme-toggle" aria-label={t('Тема')} aria-pressed={prefs.theme === 'dark'} title={t(prefs.theme === 'light' ? 'Включить тёмную тему' : 'Включить светлую тему')} onClick={() => setTheme(prefs.theme === 'light' ? 'dark' : 'light')}>
            {prefs.theme === 'light' ? <Sun size={18} aria-hidden="true"/> : <Moon size={18} aria-hidden="true"/>}
        </button>
        <label className="language-control" title={t('Язык')}>
            <span aria-hidden="true">{{kk: 'ҚАЗ', ru: 'RU', en: 'EN'}[prefs.language]}</span><ChevronDown size={12} aria-hidden="true"/>
            <select aria-label={t('Язык')} value={prefs.language} onChange={e => setLanguage(e.target.value as Language)}>
            <option value="kk">Қазақша</option><option value="ru">Русский</option><option value="en">English</option>
        </select></label>
    </div>;
}
applyDocument();
