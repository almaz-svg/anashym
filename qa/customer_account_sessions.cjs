/* Targeted session race/error injection requested by the implementation owner.
 * Uses existing isolated clients. Delayed order content is fetched from the real
 * API before its response is released; no business data are created or edited. */
const {chromium} = require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs'), path = require('path');
const BASE = 'http://127.0.0.1:5173';
const results = [];
function check(name, pass, detail) {
  results.push({name, pass: Boolean(pass), ...(detail === undefined ? {} : {detail})});
  console.log(pass ? 'PASS' : 'FAIL', name, detail || '');
  if (!pass) throw Error(name);
}
async function login(page, phone, password) {
  const inputs = await page.locator('input').evaluateAll(els => els.map(el => el.name));
  check('real login controls available', inputs.includes('phone') && inputs.includes('password'));
  await page.getByLabel('Телефон', {exact: true}).fill(phone);
  await page.getByLabel('Пароль', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Войти', exact: true}).click();
  await page.locator('header').getByRole('button', {name: 'Выйти', exact: true}).waitFor();
}
(async () => {
  const browser = await chromium.launch({headless: true});
  let page;
  try {
    const old = JSON.parse(fs.readFileSync(path.join(__dirname, 'customer-account-financial-fixture.json')));
    const next = JSON.parse(fs.readFileSync(path.join(__dirname, 'mvp-fixture.json')));
    let context = await browser.newContext({viewport: {width: 1440, height: 720}});
    page = await context.newPage();
    await page.goto(BASE); await page.waitForLoadState('networkidle');
    await login(page, old.phone, old.password);
    await page.locator('aside nav a[href="#orders"]').click();
    await page.locator('.order-button').filter({hasText: old.order_id.slice(0, 8)}).waitFor();
    await page.waitForLoadState('networkidle');
    let release, captured;
    const gate = new Promise(resolve => {release = resolve;});
    const hasCaptured = new Promise(resolve => {captured = resolve;});
    await page.route('**/api/v1/orders/' + old.order_id, async route => {
      const actual = await route.fetch();
      check('delayed order response originates from actual server', actual.status() === 200);
      captured(); await gate; await route.fulfill({response: actual});
    });
    await page.locator('.order-button').filter({hasText: old.order_id.slice(0, 8)}).click();
    await hasCaptured;
    await page.locator('header').getByRole('button', {name: 'Выйти', exact: true}).click();
    await page.getByRole('button', {name: 'Войти', exact: true}).waitFor();
    check('logout succeeds while old detail response is in flight', (await page.request.get(BASE+'/api/v1/auth/me')).status() === 401);
    await login(page, next.phone, next.password);
    await page.locator('aside nav a[href="#orders"]').click();
    const me = await (await page.request.get(BASE+'/api/v1/auth/me')).json();
    check('new session belongs to a different actual QA client', me.client_id === next.client_id && me.client_id !== old.client_id);
    const response = page.waitForResponse(r => r.url().endsWith('/api/v1/orders/' + old.order_id));
    release(); await (await response).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    check('late old order detail never appears in new client DOM', await page.getByRole('heading', {name: 'Заказ '+old.order_id.slice(0, 8), exact: true}).count() === 0 && !(await page.locator('main').innerText()).includes('QA Account '+old.tag));
    await page.screenshot({path: path.join(__dirname, 'customer-account-late-detail.png'), fullPage: false});
    await context.close();

    // Staff and a pending customer must be told when the logout request failed.
    const pending = JSON.parse(fs.readFileSync(path.join(__dirname, 'customer-account-fixture.json')));
    const admin = await browser.newContext();
    await admin.request.get(BASE+'/api/v1/auth/csrf');
    const post = async (route, data) => {
      const csrf = (await admin.cookies()).find(c => c.name === 'csrftoken').value;
      const response = await admin.request.post(BASE+'/api/v1/'+route, {headers: {'X-CSRFToken': csrf, 'Idempotency-Key': crypto.randomUUID(), Origin: BASE}, data});
      if (response.status() !== 200) throw Error(await response.text());
    };
    await post('auth/login', {phone: '+77010000002', password: 'DemoAdmin2026!'});
    await post('clients/'+pending.client_id+'/approve', {approval_status: 'pending'});
    for (const [role, phone, password] of [['staff', '+77010000004', 'DemoStaff2026!'], ['pending', pending.phone, pending.password]]) {
      context = await browser.newContext({viewport: {width: 360, height: 720}});
      page = await context.newPage();
      await page.goto(BASE); await page.waitForLoadState('networkidle'); await login(page, phone, password);
      if (role === 'pending') await page.getByText('Заявка на рассмотрении', {exact: true}).waitFor();
      await page.route('**/api/v1/auth/logout', route => route.fulfill({status: 503, contentType: 'application/json', body: JSON.stringify({code: 'QA_LOGOUT_FAILURE', message: 'QA: выход временно недоступен'})}));
      await page.locator('header').getByRole('button', {name: 'Выйти', exact: true}).click();
      const alert = page.getByRole('alert').filter({hasText: 'QA: выход временно недоступен'});
      await alert.waitFor();
      check(role+' failed logout visibly reports error', await alert.isVisible());
      check(role+' failed logout keeps actual session active', (await page.request.get(BASE+'/api/v1/auth/me')).status() === 200);
      check(role+' logout retry remains enabled', await page.locator('header').getByRole('button', {name: 'Выйти', exact: true}).isEnabled());
      await page.screenshot({path: path.join(__dirname, `customer-account-logout-503-${role}.png`), fullPage: true});
      await page.unroute('**/api/v1/auth/logout');
      await page.locator('header').getByRole('button', {name: 'Выйти', exact: true}).click();
      await page.getByRole('button', {name: 'Войти', exact: true}).waitFor();
      check(role+' retry logs out against actual server', (await page.request.get(BASE+'/api/v1/auth/me')).status() === 401);
      await context.close();
    }
    await post('clients/'+pending.client_id+'/approve', {approval_status: 'active'});
    await admin.close();
  } catch (error) {
    if (page && !page.isClosed()) await page.screenshot({path: path.join(__dirname, 'customer-account-session-failure.png'), fullPage: true});
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(__dirname, 'customer-account-session-results.json'), JSON.stringify(results, null, 2));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
