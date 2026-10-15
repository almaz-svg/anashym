const {chromium}=require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  await page.goto('http://127.0.0.1:5173');
  await page.getByLabel('Телефон',{exact:true}).fill('+77010000001');
  await page.getByLabel('Пароль',{exact:true}).fill('DemoClient2026!');
  await page.getByRole('button',{name:'Войти',exact:true}).click();
  const input=page.getByLabel('Количество: Наполеон');
  await input.waitFor();
  await input.click();
  await input.press('End');
  await input.pressSequentially('25');
  if(await input.inputValue()!=='25')throw Error('Expected 25, got '+await input.inputValue());
  await input.fill('');
  if(await input.inputValue()!=='')throw Error('Cannot clear quantity');
  await input.pressSequentially('025');
  if(await input.inputValue()!=='25')throw Error('Leading zero retained: '+await input.inputValue());
  console.log('PASS: initial typing, clearing, leading-zero normalization');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
