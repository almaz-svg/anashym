/* Real-browser acceptance. Servers must already be running. Only the uniquely
 * named QA client is created/updated; demo customers and financial history are
 * never changed. No network mocks or direct database access are used. */
const { chromium } = require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {execFileSync} = require('child_process');
const BASE = 'http://127.0.0.1:5173';
const results = [];
const evidence = [];
const fixturePath = path.join(__dirname, 'customer-account-fixture.json');
let browser, activePage;
const normalized = value => String(value).replace(/[\s\u200e\u200f]/g, '');
const formatMoney = value => new Intl.NumberFormat('ru-KZ', {style: 'currency', currency: 'KZT', maximumFractionDigits: 2}).format(Number(value));
const formatDate = value => new Date(value + 'T12:00:00').toLocaleDateString('ru-KZ');
function check(name, pass, detail) {
  results.push({name, pass: Boolean(pass), ...(detail === undefined ? {} : {detail})});
  console.log(pass ? 'PASS' : 'FAIL', name, detail === undefined ? '' : JSON.stringify(detail));
  if (!pass) throw new Error(name);
}
async function get(page, route, expected = 200) {
  const response = await page.request.get(BASE + '/api/v1/' + route);
  if (response.status() !== expected) throw new Error(`GET ${route}: ${response.status()} ${await response.text()}`);
  return expected === 204 ? null : response.json();
}
async function post(context, route, data, expected = 200) {
  const csrf = (await context.cookies()).find(cookie => cookie.name === 'csrftoken')?.value || '';
  const response = await context.request.post(BASE + '/api/v1/' + route, {
    headers: {'X-CSRFToken': csrf, 'Idempotency-Key': crypto.randomUUID(), Origin: BASE}, data,
  });
  if (response.status() !== expected) throw new Error(`POST ${route}: ${response.status()} ${await response.text()}`);
  return expected === 204 ? null : response.json();
}
async function pageFor(width, phone = '+77010000001', password = 'DemoClient2026!') {
  const context = await browser.newContext({viewport: {width, height: 720}});
  const page = activePage = await context.newPage();
  const errors = [], consoleErrors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {if (message.type() === 'error' && !/Failed to load resource: the server responded with a status of 401/.test(message.text())) consoleErrors.push(message.text());});
  await page.goto(BASE);
  await page.waitForLoadState('networkidle');
  // Inspect rendered controls before selecting them.
  const controls = await page.locator('input,button').evaluateAll(els => els.map(el => ({tag: el.tagName, name: el.name, text: el.textContent})));
  if (!controls.some(el => el.name === 'phone')) throw new Error('Login phone field missing');
  await page.getByLabel('Телефон', {exact: true}).fill(phone);
  await page.getByLabel('Пароль', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Войти', exact: true}).click();
  await page.getByRole('button', {name: 'Выйти', exact: true}).first().waitFor();
  await page.waitForLoadState('networkidle');
  return {context, page, errors, consoleErrors};
}
async function geometry(locator) {
  return locator.evaluate(el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    const range = document.createRange(); range.selectNodeContents(el);
    const textRects = [...range.getClientRects()].map(x => ({x: x.x, y: x.y, width: x.width, height: x.height, bottom: x.bottom}));
    return {text: el.textContent, x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom,
      fontSize: parseFloat(s.fontSize), color: s.color, visibility: s.visibility, display: s.display, textRects,
      withinViewport: r.x >= 0 && r.y >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1};
  });
}
async function noOverflow(page, name) {
  const dimensions = await page.evaluate(() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth}));
  check(name + ' no horizontal overflow', dimensions.scrollWidth <= dimensions.width, dimensions);
}
async function inspectAllPages(page, label) {
  const navigation = await page.locator('aside nav a').evaluateAll(links => links.map(link => ({href: link.getAttribute('href'), text: link.textContent.trim()})));
  for (const {href, text} of navigation) {
    await page.locator(`aside nav a[href="${href}"]`).click();
    await page.getByRole('heading', {name: text, exact: true}).first().waitFor();
    await page.waitForLoadState('networkidle');
    check(label + ' ' + href + ' no visible error', await page.getByRole('alert').count() === 0, await page.getByRole('alert').allTextContents());
    await noOverflow(page, label + ' ' + href);
    if (href === '#points') check(label + ' delivery addresses actually render', await page.getByRole('heading', {name: 'Добавить точку доставки', exact: true}).isVisible() && await page.locator('input[name="address"]').count() === 1);
  }
}
async function inspectHeader(page, label, requireProfile = true) {
  const header = page.locator('header').first();
  const logout = header.getByRole('button', {name: 'Выйти', exact: true});
  check(label + ' logout is in header', await logout.count() === 1);
  const g = await geometry(logout);
  check(label + ' logout text readable and wholly visible', g.fontSize >= 12 && g.withinViewport && g.visibility === 'visible' && /Выйти/.test(g.text), g);
  if (requireProfile) {
    const profile = header.getByRole('link', {name: /Профиль/});
    check(label + ' profile link in header', await profile.count() === 1);
    const p = await geometry(profile);
    check(label + ' profile link visible', p.withinViewport && p.fontSize >= 12, p);
  }
}
async function inspectFooter(page, label) {
  const footer = page.locator('footer');
  check(label + ' one footer', await footer.count() === 1);
  check(label + ' footer has About section', await footer.getByRole('heading', {name: 'О нас', exact: true}).count() === 1);
  const contact = footer.locator('a[href="mailto:almazzmusulamnkull@gmail.com"]');
  check(label + ' footer real contact email', await contact.count() === 1 && /almazzmusulamnkull@gmail.com/.test(await contact.innerText()));
  check(label + ' footer no invented telephone', await footer.locator('a[href^="tel:"]').count() === 0);
  const foot = await footer.evaluate(el => {const r = el.getBoundingClientRect(); return {bottom: r.bottom + scrollY, height: r.height, pageHeight: document.documentElement.scrollHeight, viewport: innerHeight};});
  check(label + ' footer reaches page bottom', foot.bottom >= foot.viewport - 1 && Math.abs(foot.bottom - foot.pageHeight) < 4, foot);
  await noOverflow(page, label + ' Footer');
}
async function metric(page, name, value, label, colorRule = null) {
  const article = page.getByRole('article', {name, exact: true});
  await article.waitFor();
  const text = await article.innerText();
  check(label + ' ' + name + ' equals server', normalized(text).includes(normalized(formatMoney(value))), {server: value, text});
  if (colorRule) {
    const color = await article.locator('strong').first().evaluate(el => getComputedStyle(el).color);
    const [r, g, b] = color.match(/\d+/g).map(Number);
    const red = r > g * 1.25 && r > b * 1.15;
    check(label + ' ' + name + ' ' + colorRule, colorRule === 'red' ? red : !red, {color, value});
  }
  return article;
}
async function inspectProfile(page, label) {
  await page.locator('header').getByRole('link', {name: /Профиль/}).click();
  await page.getByRole('heading', {name: 'Мой профиль', exact: true}).waitFor();
  await page.getByRole('article', {name: 'Общая задолженность', exact: true}).waitFor();
  await page.waitForLoadState('networkidle');
  const payload = await get(page, 'profile');
  evidence.push({label, profile: payload});
  const text = await page.locator('main').innerText();
  check(label + ' profile identity from server', text.includes(payload.profile.name) && text.includes(payload.profile.phone));
  check(label + ' profile exact server week', text.includes(formatDate(payload.from)) && text.includes(formatDate(payload.to)), {from: payload.from, to: payload.to});
  await metric(page, 'Общая задолженность', payload.balance.debt_amount, label, Number(payload.balance.debt_amount) > 0 ? 'red' : 'neutral');
  await metric(page, 'Аванс', payload.balance.advance_amount, label);
  await metric(page, 'Ожидает подтверждения', payload.balance.unconfirmed_payment_amount, label);
  await metric(page, 'Передано за период', payload.period.delivered_amount, label);
  await metric(page, 'Подтверждённые оплаты', payload.period.paid_amount, label);
  await metric(page, 'Осталось оплатить по поставкам периода', payload.period.outstanding_amount, label, Number(payload.period.outstanding_amount) > 0 ? 'red' : 'neutral');
  await page.getByLabel('Начало периода', {exact: true}).fill(payload.from);
  await page.getByLabel('Конец периода', {exact: true}).fill(payload.from);
  const selectedResponse = page.waitForResponse(response => response.url().includes('/api/v1/profile?from=') && response.request().method() === 'GET');
  await page.getByRole('button', {name: 'Показать период', exact: true}).click();
  await selectedResponse;
  await page.getByRole('article', {name: 'Общая задолженность', exact: true}).waitFor();
  await page.waitForLoadState('networkidle');
  const day = await get(page, 'profile?from=' + payload.from + '&to=' + payload.from);
  check(label + ' selected day matches server date inputs', await page.getByLabel('Начало периода', {exact: true}).inputValue() === day.from && await page.getByLabel('Конец периода', {exact: true}).inputValue() === day.to, {from: day.from, to: day.to});
  await metric(page, 'Передано за период', day.period.delivered_amount, label + ' selected day');
  await metric(page, 'Подтверждённые оплаты', day.period.paid_amount, label + ' selected day');
  await metric(page, 'Осталось оплатить по поставкам периода', day.period.outstanding_amount, label + ' selected day');
  await metric(page, 'Общая задолженность', payload.balance.debt_amount, label + ' selected day preserves full debt');
  const weekResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/profile') && response.request().method() === 'GET');
  await page.getByRole('button', {name: 'Текущая неделя', exact: true}).click();
  await weekResponse;
  await page.getByRole('article', {name: 'Общая задолженность', exact: true}).waitFor();
  await page.waitForLoadState('networkidle');
  await noOverflow(page, label + ' Profile');
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({path: path.join(__dirname, `customer-account-profile-${label.replace(/\W/g, '-')}-overview.png`), fullPage: false});
  await page.screenshot({path: path.join(__dirname, `customer-account-profile-${label.replace(/\W/g, '-')}.png`), fullPage: true});
  await page.locator('aside nav a[href="#catalog"]').click();
  await page.locator('aside nav a[href="#profile"]').click();
  await page.waitForLoadState('networkidle');
  check(label + ' profile also opens from navigation', /profile/.test(new URL(page.url()).hash));
  return payload;
}
async function inspectPayments(page, label) {
  await page.locator('aside nav a[href="#payments"]').click();
  await page.getByRole('heading', {name: 'Оплаты', exact: true}).waitFor();
  await page.getByRole('heading', {name: 'Сообщить об оплате Kaspi', exact: true}).waitFor();
  await page.getByRole('article', {name: 'Общая задолженность', exact: true}).waitFor();
  await page.waitForLoadState('networkidle');
  const payload = await get(page, 'profile');
  const debt = await metric(page, 'Общая задолженность', payload.balance.debt_amount, label, Number(payload.balance.debt_amount) > 0 ? 'red' : 'neutral');
  await metric(page, 'Аванс', payload.balance.advance_amount, label);
  await metric(page, 'Ожидает подтверждения', payload.balance.unconfirmed_payment_amount, label);
  await metric(page, 'Подтверждённые оплаты за неделю', payload.period.paid_amount, label);
  const summaryBox = await debt.boundingBox();
  const form = await page.getByRole('heading', {name: 'Сообщить об оплате Kaspi', exact: true}).boundingBox();
  const history = await page.getByRole('heading', {name: 'История оплат', exact: true}).boundingBox();
  check(label + ' balances precede payment form and history', summaryBox.y < form.y && summaryBox.y < history.y, {summaryY: summaryBox.y, formY: form.y, historyY: history.y});
  await noOverflow(page, label + ' Payments');
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({path: path.join(__dirname, `customer-account-payments-${label.replace(/\W/g, '-')}-overview.png`), fullPage: false});
  await page.screenshot({path: path.join(__dirname, `customer-account-payments-${label.replace(/\W/g, '-')}.png`), fullPage: true});
  return payload;
}
async function inspectDebtPage(page, label) {
  await page.locator('aside nav a[href="#debt"]').click();
  await page.getByRole('heading', {name: 'Задолженность', exact: true}).waitFor();
  await page.getByText('Текущая задолженность', {exact: true}).waitFor();
  await page.waitForLoadState('networkidle');
  const balance = await get(page, 'balance');
  const metric = page.locator('section.metric').filter({has: page.getByText('Текущая задолженность', {exact: true})});
  const text = await metric.innerText();
  const color = await metric.locator('strong').evaluate(el => getComputedStyle(el).color);
  const [r, g, b] = color.match(/\d+/g).map(Number);
  const red = r > g * 1.25 && r > b * 1.15;
  check(label + ' debt page exact amount', normalized(text).includes(normalized(formatMoney(balance.debt_amount))), {text, server: balance.debt_amount});
  check(label + ' debt page red only for positive debt', red === (Number(balance.debt_amount) > 0), {color, amount: balance.debt_amount});
  await noOverflow(page, label + ' Debt');
  await page.screenshot({path: path.join(__dirname, `customer-account-debt-${label.replace(/\W/g, '-')}.png`), fullPage: true});
}
async function inspectLogout(page, label) {
  await page.evaluate(() => scrollTo(0, 0));
  await page.locator('header').getByRole('button', {name: 'Выйти', exact: true}).click();
  await page.getByRole('button', {name: 'Войти', exact: true}).waitFor();
  const response = await page.request.get(BASE + '/api/v1/auth/me');
  check(label + ' logout invalidates server session', response.status() === 401);
  await page.reload(); await page.waitForLoadState('networkidle');
  check(label + ' reload cannot regain access', await page.getByRole('button', {name: 'Войти', exact: true}).isVisible() && await page.locator('nav').count() === 0);
}
async function closeSession(session, label) {
  check(label + ' no browser errors', session.errors.length === 0 && session.consoleErrors.length === 0, {pageErrors: session.errors, consoleErrors: session.consoleErrors});
  await session.context.close();
}
async function fixture() {
  const context = await browser.newContext();
  await context.request.get(BASE + '/api/v1/auth/csrf');
  let f;
  if (fs.existsSync(fixturePath)) f = JSON.parse(fs.readFileSync(fixturePath));
  else {
    const tag = crypto.randomUUID().slice(0, 8);
    const phone = '+778' + String(Date.now()).slice(-8);
    f = {phone, password: 'QaAccount2026!', tag};
    const user = await post(context, 'auth/register', {phone, password: f.password, name: 'QA Customer Account ' + tag, category: 'coffee_shop', description: 'Isolated customer account UI acceptance', expected_order_quantity: 10, expected_order_frequency: 'Раз в неделю', preferred_payment_mode: 'deferred', requested_period_days: 14}, 201);
    f.client_id = user.client_id;
    fs.writeFileSync(fixturePath, JSON.stringify(f, null, 2));
  }
  await post(context, 'auth/login', {phone: '+77010000002', password: 'DemoAdmin2026!'});
  await post(context, 'clients/' + f.client_id + '/approve', {approval_status: 'pending'});
  await context.close();
  return f;
}
async function run() {
  browser = await chromium.launch({headless: true});
  try {
    for (const width of [360, 768, 1440]) {
      const s = await pageFor(width);
      await inspectHeader(s.page, 'customer ' + width);
      await inspectAllPages(s.page, 'customer ' + width);
      await inspectProfile(s.page, 'customer-' + width);
      await inspectPayments(s.page, 'customer-' + width);
      await inspectDebtPage(s.page, 'customer-' + width);
      await inspectFooter(s.page, 'customer ' + width);
      await inspectLogout(s.page, 'customer ' + width);
      await closeSession(s, 'customer ' + width);
    }
    const f = await fixture();
    for (const width of [360, 768, 1440]) {
      const s = await pageFor(width, f.phone, f.password);
      check('pending ' + width + ' approval screen', (await s.page.locator('main').innerText()).includes('Заявка на рассмотрении'));
      await inspectHeader(s.page, 'pending ' + width, false);
      await noOverflow(s.page, 'pending ' + width);
      await s.page.screenshot({path: path.join(__dirname, `customer-account-pending-${width}.png`), fullPage: true});
      await inspectLogout(s.page, 'pending ' + width);
      await closeSession(s, 'pending ' + width);
    }
    const admin = await browser.newContext();
    await admin.request.get(BASE + '/api/v1/auth/csrf');
    await post(admin, 'auth/login', {phone: '+77010000002', password: 'DemoAdmin2026!'});
    await post(admin, 'clients/' + f.client_id + '/approve', {approval_status: 'active', deferred_approved: true, credit_limit_amount: '10000.00', period_days: 14});
    const zero = await pageFor(360, f.phone, f.password);
    await inspectProfile(zero.page, 'qa-zero');
    await inspectPayments(zero.page, 'qa-zero');
    await inspectDebtPage(zero.page, 'qa-zero');
    await zero.page.getByLabel('Тема', {exact: true}).selectOption('dark');
    await inspectProfile(zero.page, 'qa-zero-dark');
    await inspectPayments(zero.page, 'qa-zero-dark');
    await inspectDebtPage(zero.page, 'qa-zero-dark');
    await closeSession(zero, 'qa-zero');
    await admin.close();
    console.log(execFileSync(path.join(__dirname, '../backend/.venv/Scripts/python.exe'), [path.join(__dirname, 'customer_account_financial_fixture.py')], {encoding: 'utf8'}).trim());
    const financial = JSON.parse(fs.readFileSync(path.join(__dirname, 'customer-account-financial-fixture.json')));
    for (const width of [360, 768, 1440]) {
      const s = await pageFor(width, financial.phone, financial.password);
      const profile = await inspectProfile(s.page, 'qa-debt-' + width);
      check('qa-debt ' + width + ' debt unaffected by pending payment', profile.balance.debt_amount === financial.expected_debt && profile.balance.unconfirmed_payment_amount === financial.expected_pending, profile.balance);
      await inspectPayments(s.page, 'qa-debt-' + width);
      await inspectDebtPage(s.page, 'qa-debt-' + width);
      await s.page.getByLabel('Тема', {exact: true}).selectOption('dark');
      await inspectProfile(s.page, 'qa-debt-dark-' + width);
      await inspectPayments(s.page, 'qa-debt-dark-' + width);
      await inspectDebtPage(s.page, 'qa-debt-dark-' + width);
      await closeSession(s, 'qa-debt ' + width);
    }
    const advanceFixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'mvp-fixture.json')));
    const advance = await pageFor(360, advanceFixture.phone, advanceFixture.password);
    const advanceProfile = await inspectProfile(advance.page, 'qa-existing-advance');
    check('existing QA advance fixture has positive advance and zero debt', Number(advanceProfile.balance.advance_amount) > 0 && Number(advanceProfile.balance.debt_amount) === 0, advanceProfile.balance);
    await inspectPayments(advance.page, 'qa-existing-advance');
    await closeSession(advance, 'qa-existing-advance');
    for (const [role, index] of [['admin', 2], ['courier', 3], ['cashier', 4], ['accountant', 5]]) {
      for (const width of [360, 768, 1440]) {
        const s = await pageFor(width, '+7701000000' + index, role === 'admin' ? 'DemoAdmin2026!' : 'DemoStaff2026!');
        await noOverflow(s.page, role + ' ' + width);
        const logout = s.page.getByRole('button', {name: 'Выйти', exact: true}).first();
        const g = await geometry(logout);
        check(role + ' ' + width + ' readable accessible logout', g.fontSize >= 12 && g.withinViewport, g);
        check(role + ' ' + width + ' navigation present', await s.page.locator('nav a').count() > 0);
        const refresh = await geometry(s.page.getByRole('button', {name: 'Обновить', exact: true}).first());
        check(role + ' ' + width + ' refresh has visible text', refresh.fontSize >= 12 && refresh.withinViewport, refresh);
        await s.page.screenshot({path: path.join(__dirname, `customer-account-${role}-${width}.png`), fullPage: false});
        await closeSession(s, role + ' ' + width);
      }
    }
  } catch (error) {
    if (activePage && !activePage.isClosed()) {
      await activePage.screenshot({path: path.join(__dirname, 'customer-account-failure.png'), fullPage: true});
      fs.writeFileSync(path.join(__dirname, 'customer-account-failure.html'), await activePage.content());
    }
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(__dirname, 'customer-account-ui-results.json'), JSON.stringify({results, evidence}, null, 2));
  }
}
run().catch(error => {console.error(error); process.exitCode = 1;});
