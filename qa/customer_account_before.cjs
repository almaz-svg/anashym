const { chromium } = require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
(async () => {
  const browser = await chromium.launch({headless: true});
  const records = [];
  try {
    for (const width of [360, 768, 1440]) {
      const context = await browser.newContext({viewport: {width, height: 720}});
      const page = await context.newPage();
      await page.goto('http://127.0.0.1:5173');
      await page.waitForLoadState('networkidle');
      const initial = await page.locator('input,button').evaluateAll(els => els.map(el => ({tag: el.tagName, text: el.textContent, type: el.type, name: el.name})));
      await page.getByLabel('Телефон', {exact: true}).fill('+77010000001');
      await page.getByLabel('Пароль', {exact: true}).fill('DemoClient2026!');
      await page.getByRole('button', {name: 'Войти', exact: true}).click();
      await page.getByRole('button', {name: 'Выйти', exact: true}).waitFor();
      await page.waitForLoadState('networkidle');
      await page.screenshot({path: path.join(__dirname, `customer-account-before-${width}.png`), fullPage: false});
      const state = await page.evaluate(() => {
        const info = el => {if (!el) return null; const r = el.getBoundingClientRect(), s = getComputedStyle(el); return {tag: el.tagName, class: el.className, text: el.innerText, rect: {x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom}, fontSize: s.fontSize, display: s.display, overflow: s.overflow, height: s.height, position: s.position, color: s.color}};
        return {buttons: [...document.querySelectorAll('button')].filter(el => /Выйти|Профиль/.test(el.textContent)).map(info), aside: info(document.querySelector('aside')), nav: info(document.querySelector('nav')), header: info(document.querySelector('header')), footer: info(document.querySelector('footer')), viewport: {width: innerWidth, height: innerHeight}, scroll: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight}};
      });
      records.push({width, initial, state});
      console.log(JSON.stringify({width, state}));
      await context.close();
    }
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(__dirname, 'customer-account-before-results.json'), JSON.stringify(records, null, 2));
  }
})().catch(e => {console.error(e); process.exitCode = 1;});
