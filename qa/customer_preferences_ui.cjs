/* Real UI locale/theme checks, no submitted business forms or database writes. */
const { chromium } = require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const BASE = 'http://127.0.0.1:5173';
const languages = process.argv.includes('--ru-only') ? ['ru'] : ['kk', 'en', 'ru'];
const results = [];
let browser, activePage;
function check(name, pass, detail) {
  results.push({name, pass: Boolean(pass), ...(detail === undefined ? {} : {detail})});
  console.log(pass ? 'PASS' : 'FAIL', name, detail === undefined ? '' : JSON.stringify(detail));
  if (!pass) throw new Error(name);
}
async function controls(page) {
  // Runtime DOM reconnaissance: inspect real select options before using selectors.
  const state = await page.locator('.preferences-controls select').evaluateAll(els => els.map(el => ({label: el.getAttribute('aria-label'), values: [...el.options].map(x => x.value)})));
  check('preferences real controls available', state.length === 2 && state.some(x => x.values.join(',') === 'light,dark') && state.some(x => x.values.includes('ru') && x.values.includes('kk') && x.values.includes('en')), state);
  return {
    theme: page.locator('.preferences-controls select').filter({has: page.locator('option[value="dark"]')}),
    language: page.locator('.preferences-controls select').filter({has: page.locator('option[value="kk"]')}),
  };
}
async function noOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth}));
  check(label + ' no horizontal overflow', dimensions.scrollWidth <= dimensions.width, dimensions);
}
async function visibleLogout(page, label) {
  await page.evaluate(() => scrollTo(0, 0));
  const button = page.locator('button').filter({has: page.locator('svg.lucide-log-out')}).first();
  const state = await button.evaluate(el => {const r = el.getBoundingClientRect(), s = getComputedStyle(el); return {text: el.innerText, fontSize: parseFloat(s.fontSize), x: r.x, y: r.y, right: r.right, bottom: r.bottom, visible: r.x >= 0 && r.y >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1};});
  check(label + ' logout remains readable and visible', state.text.trim().length > 0 && state.fontSize >= 12 && state.visible, state);
}
async function assertDocument(page, language, theme, label) {
  const state = await page.evaluate(() => ({language: document.documentElement.lang, theme: document.documentElement.dataset.theme, colorScheme: document.documentElement.style.colorScheme, storedLanguage: localStorage.getItem('bakery.language'), storedTheme: localStorage.getItem('bakery.theme'), background: getComputedStyle(document.documentElement).backgroundColor, color: getComputedStyle(document.body).color}));
  check(label + ' selected locale and theme applied', state.language === language && state.theme === theme && state.colorScheme === theme, state);
  check(label + ' selections stored', state.storedLanguage === language && state.storedTheme === theme, state);
  return state;
}
async function surface(width, kind) {
  const context = await browser.newContext({viewport: {width, height: 720}});
  const page = activePage = await context.newPage(), errors = [], consoleErrors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', msg => {if (msg.type() === 'error' && !/Failed to load resource: the server responded with a status of 401/.test(msg.text())) consoleErrors.push(msg.text());});
  await page.goto(BASE); await page.waitForLoadState('networkidle');
  if (kind !== 'auth') {
    await page.getByLabel('Телефон', {exact: true}).fill(kind === 'customer' ? '+77010000001' : '+77010000004');
    await page.getByLabel('Пароль', {exact: true}).fill(kind === 'customer' ? 'DemoClient2026!' : 'DemoStaff2026!');
    await page.getByRole('button', {name: 'Войти', exact: true}).click();
    await page.getByRole('button', {name: 'Выйти', exact: true}).first().waitFor();
    await page.waitForLoadState('networkidle');
    if (kind === 'customer') {
      await page.locator('aside nav a[href="#payments"]').click();
      await page.locator('.financial-summary article').first().waitFor();
    } else await page.locator('aside nav a[href="#shifts"]').click();
    await page.waitForLoadState('networkidle');
  }
  const preference = await controls(page);
  let input, value, secondInput, secondValue;
  if (kind === 'auth') {
    input = page.locator('input[name="phone"]'); value = '+77019998877';
    secondInput = page.locator('input[name="password"]'); secondValue = 'UnsubmittedForm2026!';
  } else if (kind === 'customer') {
    input = page.locator('input[name="amount"]'); value = '12.34';
    secondInput = page.locator('input[name="reference"]'); secondValue = 'QA preference draft';
  } else {
    const fields = await page.locator('form input').evaluateAll(els => els.map(el => ({name: el.name, type: el.type, value: el.value})));
    check('staff editable real form available', fields.length > 0, fields);
    input = page.locator('form input[type="number"]').first(); value = '123.45';
  }
  await input.fill(value);
  if (secondInput) await secondInput.fill(secondValue);
  const chrome = () => kind === 'auth' ? page.locator('.auth-form h2').innerText() : page.locator('h1').first().innerText();
  const baselineText = await chrome();
  const states = {};
  for (const language of languages) {
    await preference.language.scrollIntoViewIfNeeded();
    await preference.language.focus();
    await preference.language.selectOption(language);
    for (const theme of ['light', 'dark']) {
      await preference.theme.scrollIntoViewIfNeeded();
      await preference.theme.focus();
      await preference.theme.selectOption(theme);
      const label = `${kind}-${width}-${language}-${theme}`;
      states[language + '-' + theme] = await assertDocument(page, language, theme, label);
      check(label + ' filled form preserved', await input.inputValue() === value && (!secondInput || await secondInput.inputValue() === secondValue));
      const currentText = await chrome();
      check(label + ' page heading translated', language === 'ru' ? currentText === baselineText : currentText !== baselineText, {baseline: baselineText, actual: currentText});
      if (kind !== 'auth') await visibleLogout(page, label);
      await noOverflow(page, label);
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path: path.join(__dirname, `customer-preferences-${label}.png`), fullPage: false});
    }
  }
  check(`${kind}-${width} theme changes actual background`, states['ru-light'].background !== states['ru-dark'].background, {light: states['ru-light'], dark: states['ru-dark']});
  // Persist each selected language across a real page reload, keeping dark theme.
  for (const language of languages) {
    await preference.language.selectOption(language);
    await page.reload(); await page.waitForLoadState('networkidle');
    await assertDocument(page, language, 'dark', `${kind}-${width}-${language} reload`);
    await noOverflow(page, `${kind}-${width}-${language} reload`);
    if (kind !== 'auth') await visibleLogout(page, `${kind}-${width}-${language} reload`);
  }
  await preference.theme.selectOption('light');
  await page.reload(); await page.waitForLoadState('networkidle');
  await assertDocument(page, 'ru', 'light', `${kind}-${width} light reload`);
  check(`${kind}-${width} no browser errors`, errors.length === 0 && consoleErrors.length === 0, {errors, consoleErrors});
  await context.close();
}
(async () => {
  browser = await chromium.launch({headless: true});
  try {
    for (const width of [360, 768, 1440]) for (const kind of ['auth', 'customer', 'staff']) await surface(width, kind);
  } catch (error) {
    if (activePage && !activePage.isClosed()) {
      await activePage.screenshot({path: path.join(__dirname, 'customer-preferences-failure.png'), fullPage: true});
      fs.writeFileSync(path.join(__dirname, 'customer-preferences-failure.html'), await activePage.content());
    }
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(__dirname, process.argv.includes('--ru-only') ? 'customer-preferences-ru-results.json' : 'customer-preferences-ui-results.json'), JSON.stringify(results, null, 2));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
