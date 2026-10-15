const {chromium}=require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
const results=[];
function check(name,pass,detail){results.push({name,pass,detail});console.log(pass?'PASS':'FAIL',name,detail||'');if(!pass)throw Error(name)}
(async()=>{const browser=await chromium.launch({headless:true});try{
for(const width of [1440,768,360])for(const [role,n,password] of [['customer',1,'DemoClient2026!'],['admin',2,'DemoAdmin2026!'],['courier',3,'DemoStaff2026!'],['cashier',4,'DemoStaff2026!'],['accountant',5,'DemoStaff2026!']]){
const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:5173');await page.waitForLoadState('networkidle');
await page.getByLabel('Телефон',{exact:true}).fill('+7701000000'+n);await page.getByLabel('Пароль',{exact:true}).fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();
await page.getByRole('button',{name:'Выйти',exact:true}).waitFor();await page.waitForLoadState('networkidle');
check(`${role} ${width} login real session`,await page.getByRole('button',{name:'Выйти',exact:true}).isVisible());
const links=await page.locator('nav a').allTextContents();
for(const name of links){await page.getByRole('link',{name,exact:true}).click();await page.waitForLoadState('networkidle');
check(`${role} ${width} ${name} no error`,await page.getByRole('alert').count()===0,await page.getByRole('alert').allTextContents());
check(`${role} ${width} ${name} no overflow`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
}
await page.screenshot({path:path.join(__dirname,`mvp-${role}-${width}.png`),fullPage:true});
check(`${role} ${width} no page errors`,errors.length===0,errors);
await context.close();
}
}finally{await browser.close();fs.writeFileSync(path.join(__dirname,'mvp-browser-results.json'),JSON.stringify(results,null,2))}})().catch(e=>{console.error(e);process.exitCode=1});
