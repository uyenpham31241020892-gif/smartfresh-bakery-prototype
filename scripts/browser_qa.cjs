const {chromium}=require('playwright');const fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({...(process.env.SMARTFRESH_CHROMIUM?{executablePath:process.env.SMARTFRESH_CHROMIUM}:{}),args:['--no-sandbox','--disable-gpu'],headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000');await page.locator('#auth-form').waitFor();
 await page.locator('[name=username]').fill('manager');await page.locator('[name=password]').fill('demo12345');await page.locator('#auth-form button[type=submit]').click();
 await page.waitForFunction(()=>typeof state!=='undefined'&&state?.plan?.length===7,{timeout:30000});
 fs.mkdirSync('runtime/qa/screens',{recursive:true});const views=['overview','m2','m1','ledger','reports','data','safety','monitoring','registry','learning','readiness','audit','settings'];const results=[];
 for(const view of views){
  await page.evaluate(async v=>{await go(v)},view);
  await page.waitForTimeout(500);
  const text=await page.locator('#view').innerText();if(!text.trim())throw Error('Empty '+view);
  if(text.includes('undefined')||text.includes('NaN'))throw Error('Invalid content '+view+': '+text.slice(0,300));
  await page.screenshot({path:'runtime/qa/screens/'+view+'.png',fullPage:true});results.push({view,ok:true});
 }
 // Exercise the actual production approval modal and the price dropdown in the DOM.
 await page.evaluate(()=>go('m2'));await page.locator('[data-approve=plan]').click();await page.locator('#confirm-approval').click();
 await page.waitForFunction(()=>state.phase==='plan_approved');await page.locator('[data-act=prepared]').click();await page.locator('#confirm-action').click();
 await page.waitForFunction(()=>state.phase==='running');
 await page.evaluate(async()=>{await api('/api/realtime/'+state.id,{enabled:false});await manualAdvance(1170);await go('m1')});
 page.once('dialog',d=>d.accept('Manager điều chỉnh vì tồn cao'));
 await page.locator('[data-safety-post=mode][data-value=manual]').click();
 await page.waitForFunction(()=>state.safety.mode==='manual'&&state.pending?.rows?.length>0);
 const sku=await page.locator('[data-discount]').first().getAttribute('data-discount');
 await page.locator('[data-discount]').first().locator('..').evaluate(el=>el.open=true);
 await page.locator('[data-discount]').first().selectOption('30');
 if(await page.locator('[data-discount]').first().inputValue()!=='30')throw Error('Manager dropdown cannot select 30');
 await page.locator('[data-approve=price]').click();await page.locator('#approval-reason').fill('Tồn cao, Manager chọn 30 phần trăm');await page.locator('#confirm-approval').click();
 await page.waitForFunction(()=>state.phase==='price_approved');
 await page.locator('[data-act=price_apply]').click();await page.locator('#confirm-action').click();
 await page.waitForFunction(s=>state.products[s].discount===30,sku);
 await page.screenshot({path:'runtime/qa/screens/m1_applied.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'runtime/qa/screens/mobile.png',fullPage:true});
 results.push({flow:'Original UI approval + Manager dropdown30 + apply',ok:true});
 fs.writeFileSync('runtime/qa/BROWSER_QA.json',JSON.stringify({browser:await browser.version(),views:results,errors,passed:errors.length===0},null,2));
 console.log(JSON.stringify({results,errors}));await browser.close();if(errors.length)process.exit(1);
})().catch(e=>{console.error(e.stack);process.exit(1)});
