/* Narrow layout/auth regression for compact controls. Existing server only;
 * no business mutations, new clients, finance operations, or network mocks. */
const {chromium} = require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs'), path = require('path');
const BASE = 'http://127.0.0.1:5173';
const results = [], geometryEvidence = [];
const words = {
  ru: {theme: 'Тема', language: 'Язык', logout: 'Выйти', profile: 'Профиль', login: 'Вход', register: 'Регистрация', invite: 'У меня есть приглашение', back: 'Вернуться ко входу'},
  kk: {theme: 'Тақырып', language: 'Тіл', logout: 'Шығу', profile: 'Профиль', login: 'Кіру', register: 'Тіркелу', invite: 'Менде шақыру бар', back: 'Кіруге оралу'},
  en: {theme: 'Theme', language: 'Language', logout: 'Sign out', profile: 'Profile', login: 'Sign in', register: 'Register', invite: 'I have an invitation', back: 'Back to sign in'},
};
let page, browser;
function check(name, pass, detail) {
  results.push({name, pass: Boolean(pass), ...(detail === undefined ? {} : {detail})});
  console.log(pass ? 'PASS' : 'FAIL', name, detail === undefined ? '' : JSON.stringify(detail));
  if (!pass) throw Error(name);
}
const languageControl = () => page.locator('.preferences-controls select');
const themeControl = () => page.locator('.preferences-controls button[aria-pressed]');
async function noOverflow(label) {
  const d = await page.evaluate(() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth}));
  check(label+' no horizontal overflow', d.scrollWidth <= d.width, d);
}
async function inspectControls(language, theme, label) {
  const state = await page.locator('.preferences-controls').evaluate(el => ({buttons: [...el.querySelectorAll('button')].map(b => ({label: b.getAttribute('aria-label'), pressed: b.getAttribute('aria-pressed')})), selects: [...el.querySelectorAll('select')].map(s => ({label: s.getAttribute('aria-label'), value: s.value, text: (s.closest('label')?.querySelector('span')?.textContent||s.selectedOptions[0]?.textContent)?.trim(), options: [...s.options].map(o => o.value)}))}));
  check(label+' one accessible theme button and one native language select', state.buttons.length === 1 && state.selects.length === 1 && state.buttons[0].label === words[language].theme && state.selects[0].label === words[language].language, state);
  check(label+' language displays short code', state.selects[0].value === language && state.selects[0].text.length <= 3, state.selects[0]);
  check(label+' theme pressed state matches appearance', state.buttons[0].pressed === String(theme === 'dark'));
  const doc = await page.evaluate(() => ({language: document.documentElement.lang, theme: document.documentElement.dataset.theme, savedLanguage: localStorage.getItem('bakery.language'), savedTheme: localStorage.getItem('bakery.theme')}));
  check(label+' settings applied and persisted', doc.language === language && doc.theme === theme && doc.savedLanguage === language && doc.savedTheme === theme, doc);
}
async function setTheme(theme) {
  if (await themeControl().getAttribute('aria-pressed') !== String(theme === 'dark')) await themeControl().click();
  await page.waitForFunction(value => document.documentElement.dataset.theme === value, theme);
}
async function capture(kind, width, language, theme) {
  if (![360,1440].includes(width)) return;
  await page.evaluate(() => {document.activeElement?.blur(); scrollTo(0,0);});
  await page.screenshot({path: path.join(__dirname, `compact-${kind}-${width}-${language}-${theme}.png`), fullPage: false});
  if (kind === 'auth') await page.locator('.auth-form').screenshot({path: path.join(__dirname, `compact-auth-form-${width}-${language}-${theme}.png`)});
}
async function inspectHeader(width, language, theme) {
  await page.evaluate(() => scrollTo(0,0));
  const label = `header ${width} ${language} ${theme}`;
  const header = page.locator('header.account-header');
  const g = await header.evaluate(el => {
    const box = node => {const r = node.getBoundingClientRect(), s = getComputedStyle(node); return {tag: node.tagName, text: node.textContent.trim(), x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,font:parseFloat(s.fontSize),display:s.display,visibility:s.visibility};};
    const controls = [...el.querySelectorAll('a,button,select')].map(box);
    const bounds = box(el);
    return {header:bounds,controls,viewport:{width:innerWidth,height:innerHeight},overlaps:controls.flatMap((a,i)=>controls.slice(i+1).filter(b=>Math.min(a.right,b.right)-Math.max(a.x,b.x)>1 && Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>1).map(b=>[a.text,b.text]))};
  });
  geometryEvidence.push({label,...g});
  check(label+' compact header height', g.header.height <= (width <= 768 ? 80 : 90), g.header);
  check(label+' controls fit header without overlap', g.overlaps.length === 0 && g.controls.every(c=>c.x >= g.header.x-1 && c.right <= g.header.right+1 && c.y >= g.header.y-1 && c.bottom <= g.header.bottom+1), g);
  const logout = page.getByRole('button', {name:words[language].logout,exact:true});
  check(label+' exactly one sign-out action', await logout.count() === 1 && await header.getByRole('button', {name:words[language].logout,exact:true}).count() === 1);
  const out = await logout.evaluate(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{text:el.innerText,font:parseFloat(s.fontSize),visible:r.x>=0&&r.y>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1,width:r.width,height:r.height};});
  check(label+' sign-out text visible', out.text.trim().length>0 && out.font>=12 && out.visible, out);
  const identity = header.locator('a.account-identity[href="#profile"]');
  check(label+' identity is accessible profile link', await identity.count()===1 && await identity.evaluate(el=>Boolean((el.getAttribute('aria-label')||el.textContent).trim())&&el.tabIndex>=0));
  await inspectControls(language,theme,label);
  await noOverflow(label);
}
async function assertAuthMode(mode, label) {
  const state = await page.locator('.auth-form form').evaluate(form=>({fields:[...form.querySelectorAll('input,select,textarea')].map(x=>x.name),minLength:form.querySelector('input[name="password"]').minLength}));
  const has = name => state.fields.includes(name);
  check(label+' correct '+mode+' fields', has('password') && (mode==='invitation' ? has('token')&&!has('phone')&&!has('name')&&state.minLength===12 : has('phone')&&!has('token')&&(mode==='register' ? has('name')&&has('description')&&state.minLength===8 : !has('name')&&!has('description')&&state.minLength===1)),state);
}
async function authModes(language,width) {
  const w=words[language], label=`auth modes ${width} ${language}`;
  const tabs=page.locator('.tabs');
  check(label+' only sign-in and registration are primary tabs', await tabs.getByRole('button').count()===2 && await tabs.getByRole('button',{name:w.login,exact:true}).count()===1 && await tabs.getByRole('button',{name:w.register,exact:true}).count()===1);
  const invitation=page.getByRole('button',{name:w.invite,exact:true});
  check(label+' invitation is outside primary tabs', await invitation.count()===1 && await invitation.evaluate(el=>!el.closest('.tabs')));
  const empty = async (field, transition) => check(label+' '+transition+' clears previous mode values',await page.locator(`input[name="${field}"]`).inputValue()===''&&await page.locator('input[name="password"]').inputValue()==='');
  await page.locator('input[name="phone"]').fill('+77018887766'); await page.locator('input[name="password"]').fill('PhoneDraft2026!');
  await invitation.click(); await assertAuthMode('invitation',label); await empty('token','login to invitation');
  await page.locator('input[name="token"]').fill('qa-token-must-not-become-phone'); await page.locator('input[name="password"]').fill('TokenDraft2026!');
  await tabs.getByRole('button',{name:w.register,exact:true}).click(); await assertAuthMode('register',label); await empty('phone','invitation to registration');
  await page.locator('input[name="phone"]').fill('+77017776655'); await page.locator('input[name="password"]').fill('RegisterDraft2026!');
  await page.getByRole('button',{name:w.invite,exact:true}).click(); await assertAuthMode('invitation',label); await empty('token','registration to invitation');
  await page.locator('input[name="token"]').fill('qa-another-token'); await page.locator('input[name="password"]').fill('OtherTokenDraft2026!');
  await tabs.getByRole('button',{name:w.login,exact:true}).click(); await assertAuthMode('login',label); await empty('phone','invitation to login');
  await page.getByRole('button',{name:w.invite,exact:true}).click();
  await page.locator('input[name="token"]').fill('qa-back-token');
  await page.getByRole('button',{name:w.back,exact:true}).click(); await assertAuthMode('login',label+' back'); await empty('phone','invitation back');
}
async function runWidth(width) {
  const context=await browser.newContext({viewport:{width,height:720}}),errors=[];
  page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',msg=>{if(msg.type()==='error'&&!/Failed to load resource: the server responded with a status of 401/.test(msg.text()))errors.push(msg.text());});
  await page.goto(BASE); await page.waitForLoadState('networkidle');
  // Inspect actual controls before using their selectors.
  const initial=await page.locator('.preferences-controls').innerText();
  check(`auth ${width} rendered preferences`,Boolean(initial.trim()));
  for(const language of ['ru','kk','en']) {
    await page.locator('input[name="phone"]').fill('+77019998877');
    await page.locator('input[name="password"]').fill('UnsubmittedDraft2026!');
    await languageControl().selectOption(language);
    check(`auth ${width} ${language} language preserves filled fields`,await page.locator('input[name="phone"]').inputValue()==='+77019998877'&&await page.locator('input[name="password"]').inputValue()==='UnsubmittedDraft2026!');
    // Toggle once even from default light so persistence is exercised by a click.
    await setTheme('dark');
    for(const theme of ['light','dark']) {
      await setTheme(theme); await inspectControls(language,theme,`auth ${width} ${language} ${theme}`);
      check(`auth ${width} ${language} ${theme} theme preserves form`,await page.locator('input[name="phone"]').inputValue()==='+77019998877'&&await page.locator('input[name="password"]').inputValue()==='UnsubmittedDraft2026!');
      await noOverflow(`auth ${width} ${language} ${theme}`); await capture('auth',width,language,theme);
    }
    await page.reload(); await page.waitForLoadState('networkidle'); await inspectControls(language,'dark',`auth ${width} ${language} dark reload`);
    await authModes(language,width);
    await setTheme('light'); await page.reload(); await page.waitForLoadState('networkidle'); await inspectControls(language,'light',`auth ${width} ${language} light reload`);
  }
  await page.locator('input[name="phone"]').fill('+77010000001');
  await page.locator('input[name="password"]').fill('DemoClient2026!');
  const signedIn=page.waitForResponse(r=>r.url().endsWith('/api/v1/auth/login')&&r.request().method()==='POST');
  await page.locator('.auth-form form button[type="submit"],.auth-form form button.primary').click();
  check(`customer ${width} actual login`,(await signedIn).status()===200);
  await page.locator('header.account-header').waitFor();
  await page.locator('header a.account-identity').click();
  await page.locator('#customer-profile-title').waitFor();
  await page.locator('#account-balance-title').waitFor();
  check(`customer ${width} identity opens profile`,new URL(page.url()).hash==='#profile');
  for(const language of ['ru','kk','en']) {
    const dates=page.locator('.account-period-form input[type="date"]');
    await dates.nth(0).fill('2026-10-01');await dates.nth(1).fill('2026-10-07');
    await languageControl().selectOption(language);
    check(`profile ${width} ${language} language preserves dates`,await dates.nth(0).inputValue()==='2026-10-01'&&await dates.nth(1).inputValue()==='2026-10-07');
    for(const theme of ['light','dark']) {
      await setTheme(theme);await inspectHeader(width,language,theme);
      check(`profile ${width} ${language} ${theme} theme preserves dates`,await dates.nth(0).inputValue()==='2026-10-01'&&await dates.nth(1).inputValue()==='2026-10-07');
      await capture('profile',width,language,theme);
    }
    await page.reload();await page.waitForLoadState('networkidle');await page.locator('#account-balance-title').waitFor();await inspectHeader(width,language,'dark');
  }
  const signedOut=page.waitForResponse(r=>r.url().endsWith('/api/v1/auth/logout')&&r.request().method()==='POST');
  await page.locator('header').getByRole('button',{name:words.en.logout,exact:true}).click();
  check(`customer ${width} actual logout`,(await signedOut).status()===204);
  await page.locator('.auth-form input[name="phone"]').waitFor();
  check(`customer ${width} server session gone`,(await page.request.get(BASE+'/api/v1/auth/me')).status()===401);
  await page.reload();await page.waitForLoadState('networkidle');
  check(`customer ${width} reload stays signed out`,await page.locator('.auth-form input[name="phone"]').isVisible()&&await page.locator('header.account-header').count()===0);
  check(`${width} no browser errors`,errors.length===0,errors);await context.close();
}
(async()=>{
  browser=await chromium.launch({headless:true});
  try {for(const width of [360,768,1440])await runWidth(width);}
  catch(error){if(page&&!page.isClosed()){await page.screenshot({path:path.join(__dirname,'compact-account-failure.png'),fullPage:true});fs.writeFileSync(path.join(__dirname,'compact-account-failure.html'),await page.content());}throw error;}
  finally{await browser.close();fs.writeFileSync(path.join(__dirname,'compact-account-ui-results.json'),JSON.stringify({results,geometryEvidence},null,2));}
})().catch(error=>{console.error(error);process.exitCode=1;});
