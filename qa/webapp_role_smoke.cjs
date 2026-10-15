/* Read-only browser smoke across the five demo roles. Reuses the project's
 * installed Playwright runtime. Only login/logout requests write server state;
 * no orders, payments, approvals, or other business records are changed. */
const {chromium} = require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const BASE = 'http://localhost:5173';
const results = [], pages = [], network = [];
const startedAt = new Date().toISOString();
function check(name, pass, detail) {
  results.push({name, pass: Boolean(pass), detail});
  console.log(pass ? 'PASS' : 'FAIL', name);
  if (!pass) throw new Error(name + ': ' + JSON.stringify(detail));
}
async function financialCard(page, name, amount) {
  const card = page.getByRole('article', {name, exact:true});
  await card.waitFor();
  const expected = new Intl.NumberFormat('ru-KZ', {style:'currency',currency:'KZT',maximumFractionDigits:2}).format(Number(amount));
  const normalize = text => text.replace(/[\s\u200e\u200f]/g, '');
  check(name + ' agrees with live API', normalize(await card.innerText()).includes(normalize(expected)), {amount});
}
(async () => {
  const browser = await chromium.launch({headless:true});
  let activePage;
  try {
    for (const [role,index,password] of [
      ['customer',1,'DemoClient2026!'], ['admin',2,'DemoAdmin2026!'],
      ['courier',3,'DemoStaff2026!'], ['cashier',4,'DemoStaff2026!'], ['accountant',5,'DemoStaff2026!']
    ]) for (const width of [360,1440]) {
      const context = await browser.newContext({viewport:{width,height:800}});
      const page = activePage = await context.newPage();
      const errors = [], badResponses = [];
      let phase = 'initial';
      const requestPhases = new Map();
      const inFlight = new Set();
      let lastNetworkActivity = Date.now();
      page.on('request', request => {
        requestPhases.set(request, phase);
        inFlight.add(request); lastNetworkActivity=Date.now();
      });
      const finished = request => {inFlight.delete(request);lastNetworkActivity=Date.now();};
      page.on('requestfinished', finished); page.on('requestfailed', finished);
      async function settleRequests() {
        // Track requests explicitly for hash navigation. The browser's original
        // document networkidle lifecycle event may already have fired.
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const deadline = Date.now()+15000;
        while (inFlight.size || Date.now()-lastNetworkActivity < 200) {
          if (Date.now()>deadline) throw new Error('Requests did not settle: '+[...inFlight].map(r=>r.url()).join(', '));
          await new Promise(resolve=>setTimeout(resolve,50));
        }
      }
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => {
        if (response.url().includes('/api/v1/')) network.push({role,width,url:response.url(),status:response.status(),started:requestPhases.get(response.request()),finished:phase});
        const expectedLogoutFailure = requestPhases.get(response.request()) === 'injected logout failure' && response.status() === 503 && response.url().endsWith('/auth/logout');
        if (response.url().includes('/api/v1/') && response.status() >= 400 && !(response.status() === 401 && response.url().endsWith('/auth/me')) && !expectedLogoutFailure) {
          badResponses.push({url:response.url(),status:response.status(),started:requestPhases.get(response.request()),finished:phase});
        }
      });
      page.on('console', message => {
        const expected = /Failed to load resource: the server responded with a status of 401/.test(message.text()) || (phase==='injected logout failure' && /Failed to load resource: the server responded with a status of 503/.test(message.text()));
        if (message.type()==='error' && !expected) errors.push(message.text());
      });
      await page.goto(BASE); await page.waitForLoadState('networkidle');
      const fields = await page.locator('.auth-form input').evaluateAll(nodes => nodes.map(node => node.name));
      check(role+' '+width+' login fields rendered', fields.includes('phone') && fields.includes('password'));
      await page.getByLabel('Телефон', {exact:true}).fill('+7701000000'+index);
      await page.getByLabel('Пароль', {exact:true}).fill(password);
      phase = 'login';
      await page.getByRole('button',{name:'Войти',exact:true}).click();
      await page.locator('header.account-header').waitFor();
      await page.waitForLoadState('networkidle');
      await settleRequests();
      const identityResponse = await page.request.get(BASE+'/api/v1/auth/me');
      const identity = await identityResponse.json();
      check(role+' '+width+' correct real account', identityResponse.status()===200 && identity.role===role, {role:identity.role});
      const navigation = await page.locator('aside nav a').evaluateAll(nodes => nodes.map(node => ({href:node.getAttribute('href'),text:node.textContent.trim()})));
      check(role+' '+width+' has workspace navigation', navigation.length > 0);
      for (const link of navigation) {
        const label = role+' '+width+' '+link.href;
        phase = link.href;
        // A previously reached networkidle state can resolve immediately before
        // React's navigation effects begin. Wait for this navigation's response
        // first so data (including StrictMode's repeat request) really settle.
        const alreadyOpen = await page.getByRole('heading',{level:1,name:link.text,exact:true}).count() > 0;
        const response = alreadyOpen ? null : page.waitForResponse(r => r.url().includes('/api/v1/') && r.request().method()==='GET');
        await page.locator('aside nav a[href="'+link.href+'"]').click();
        await page.getByRole('heading',{level:1,name:link.text,exact:true}).waitFor();
        if (response) await (await response).finished();
        await page.waitForLoadState('networkidle');
        await settleRequests();
        check(label+' no visible error', await page.getByRole('alert').count()===0, await page.getByRole('alert').allTextContents());
        const bounds = await page.evaluate(() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
        check(label+' fits screen', bounds.scrollWidth <= bounds.width, bounds);
        check(label+' footer contact available', await page.locator('footer a[href="mailto:almazzmusulamnkull@gmail.com"]').count()===1);
        pages.push({role,width,route:link.href,title:link.text});
        if (link.href==='#payments') {
          const duplicates = await page.locator('.record').evaluateAll(records => records.flatMap((record,index) => {
            const labels=[...record.querySelectorAll('small')].map(node=>node.textContent.trim());
            return labels.filter(label=>label==='Сумма').length>1 || (labels.includes('Статус') && labels.includes('Состояние проверки')) ? [index] : [];
          }));
          check(label+' payment amount and status are not duplicated', duplicates.length===0, duplicates);
        }
        if (role==='customer' && ['#profile','#payments'].includes(link.href)) {
          const response = await page.request.get(BASE+'/api/v1/profile');
          check(label+' profile API ready', response.status()===200);
          const data = await response.json();
          await financialCard(page,'Общая задолженность',data.balance.debt_amount);
          await financialCard(page,'Аванс',data.balance.advance_amount);
          await financialCard(page,'Ожидает подтверждения',data.balance.unconfirmed_payment_amount);
          if (link.href==='#profile') {
            await financialCard(page,'Осталось оплатить по поставкам периода',data.period.outstanding_amount);
            await page.getByLabel('Начало периода',{exact:true}).fill('2026-10-10');
            await page.getByLabel('Конец периода',{exact:true}).fill('2026-10-01');
            check(label+' reversed dates blocked', await page.getByRole('button',{name:'Показать период',exact:true}).isDisabled() && await page.getByRole('alert').count()===1);
            await page.getByRole('button',{name:'Текущая неделя',exact:true}).click();
            await page.waitForLoadState('networkidle');
            await settleRequests();
          }
        }
        if (role==='customer' && link.href==='#catalog') {
          const quantity = page.locator('.quantity input').first();
          if (await quantity.count()) {
            await quantity.fill(''); await quantity.pressSequentially('25');
            check(label+' no leading zero during typing',await quantity.inputValue()==='25');
            await quantity.fill('');
            check(label+' quantity can be cleared',await quantity.inputValue()==='');
          }
        }
        if (link===navigation[0] || (role==='customer' && link.href==='#payments')) {
          await page.evaluate(() => scrollTo(0,0));
          await page.screenshot({path:path.join(__dirname,`webapp-${role}-${width}-${link.href.slice(1)}.png`),fullPage:false});
        }
      }
      await page.evaluate(() => scrollTo(0,0));
      await settleRequests();
      const logout = page.locator('header').getByRole('button',{name:'Выйти',exact:true});
      check(role+' '+width+' single visible logout',await logout.count()===1 && await logout.isVisible());
      // Simulate a transport failure in this isolated browser; verify recovery
      // without changing any account or business record on the server.
      if (role==='cashier' && width===360) {
        phase = 'injected logout failure';
        await page.route('**/api/v1/auth/logout',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'QA: выход временно недоступен'})}));
        await logout.click();
        await page.getByRole('alert').filter({hasText:'QA: выход временно недоступен'}).waitFor();
        check('failed logout reports failure and retains session',(await page.request.get(BASE+'/api/v1/auth/me')).status()===200 && await logout.isEnabled());
        await page.unroute('**/api/v1/auth/logout');
      }
      phase = 'logout';
      await logout.click();
      await page.locator('.auth-form input[name="phone"]').waitFor();
      check(role+' '+width+' logout ends server session',(await page.request.get(BASE+'/api/v1/auth/me')).status()===401);
      await page.reload(); await page.waitForLoadState('networkidle');
      check(role+' '+width+' reload remains signed out',await page.locator('header.account-header').count()===0 && await page.locator('.auth-form').isVisible());
      check(role+' '+width+' no unexpected browser or HTTP errors',errors.length===0 && badResponses.length===0,{errors,badResponses});
      await context.close();
    }
  } catch(error) {
    if (activePage && !activePage.isClosed()) await activePage.screenshot({path:path.join(__dirname,'webapp-role-smoke-failure.png'),fullPage:true});
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(__dirname,'webapp-role-smoke-results.json'),JSON.stringify({startedAt,finishedAt:new Date().toISOString(),results,pages,network},null,2));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
