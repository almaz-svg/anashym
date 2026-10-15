const {chromium}=require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
const path=require('path');
const out=__dirname;
const results=[];
function check(name,pass,detail){results.push({name,pass,detail});console.log(`${pass?'PASS':'FAIL'} ${name}`,detail||'');if(!pass)throw new Error(name)}
(async()=>{
 const browser=await chromium.launch({headless:true});let currentPage;
 try{
  for(const width of [1440,360]){
   const context=await browser.newContext({viewport:{width,height:900}});
   const page=await context.newPage();currentPage=page;const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('401 (Unauthorized)'))errors.push(m.text())});
   await page.goto('http://127.0.0.1:5173');await page.waitForLoadState('networkidle');
   await page.screenshot({path:path.join(out,`login-${width}.png`),fullPage:true});
   check(`login ${width} no overflow`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.getByLabel('Телефон',{exact:true}).fill('+77010000001');
   await page.getByLabel('Пароль',{exact:true}).fill('DemoClient2026!');
   await page.getByRole('button',{name:'Войти',exact:true}).click();
   await page.getByRole('heading',{name:'Поставка начинается здесь'}).waitFor();await page.waitForLoadState('networkidle');
   await page.locator('.product').first().waitFor();
   check(`catalog ${width} three products`,await page.locator('.product').count()===3);
   check(`catalog ${width} no overflow`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(out,`catalog-${width}.png`),fullPage:true});
   if(width===1440){
    const tomorrow=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Almaty',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(Date.now()+86400000));
    await Promise.all([page.waitForResponse(r=>r.url().includes('/catalog?delivery_date='+tomorrow)),page.getByLabel('Дата поставки').fill(tomorrow)]);await page.waitForLoadState('networkidle');
    await page.getByLabel('Количество: Медовик').fill('1');
    await page.getByRole('button',{name:'Заказать с отсрочкой'}).click();
    await page.getByText('На рассмотрении, зарезервирован',{exact:true}).waitFor();await page.waitForLoadState('networkidle');
    check('order server confirmation',await page.getByRole('heading',{name:'История заказов'}).isVisible());
    await page.screenshot({path:path.join(out,'order-1440.png'),fullPage:true});
   }
   await page.getByRole('link',{name:'Задолженность',exact:true}).click();
   await page.getByRole('heading',{name:'Условия расчётов'}).waitFor();await page.waitForLoadState('networkidle');
   check(`debt ${width} no overflow`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   check(`debt ${width} separate payments`,await page.getByRole('link',{name:'Оплаты',exact:true}).isVisible());
   await page.screenshot({path:path.join(out,`debt-${width}.png`),fullPage:true});
   await page.getByRole('button',{name:'Выйти',exact:true}).click();
   await page.getByRole('button',{name:'Регистрация',exact:true}).click();
   await page.getByRole('combobox',{name:/Категория/}).selectOption('other');
   check(`registration ${width} other required`,await page.getByLabel('Уточните категорию').getAttribute('required')!==null);
   await page.getByLabel('Телефон',{exact:true}).fill('+77'+String(Math.floor(Math.random()*1e9)).padStart(9,'0'));
   await page.getByLabel('Пароль',{exact:true}).fill('QaUi2026!');
   await page.getByLabel('Название или имя').fill('QA browser '+width);
   await page.getByLabel('Уточните категорию').fill('Тестовая категория');
   await page.getByLabel('Описание деятельности').fill('Browser test only');
   await page.getByLabel('Порций за заказ').fill('5');
   await page.screenshot({path:path.join(out,`registration-${width}.png`),fullPage:true});
   await page.getByRole('button',{name:'Отправить заявку'}).click();
   await page.getByRole('heading',{name:'Спасибо за знакомство!'}).waitFor();await page.waitForLoadState('networkidle');
   check(`registration ${width} pending screen`,await page.getByText('Заявка на рассмотрении',{exact:true}).isVisible());
   check(`pending ${width} no overflow`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(out,`pending-${width}.png`),fullPage:true});
   check(`browser ${width} no unexpected console/page errors`,errors.length===0,errors);
   await context.close();
  }
 }catch(e){if(currentPage){await currentPage.screenshot({path:path.join(out,'ui-failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'ui-failure.html'),await currentPage.content());}throw e;}finally{await browser.close();fs.writeFileSync(path.join(out,'ui-results.json'),JSON.stringify(results,null,2))}
})().catch(e=>{console.error(e);process.exit(1)});


