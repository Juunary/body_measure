/* Run with Node + Playwright. Uses an isolated server/database, never user records. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs/promises');
const path=require('node:path');
const studio=path.resolve(__dirname,'..');
const origin=process.env.PASSPORT_TEST_ORIGIN||'http://127.0.0.1:8011';
const port=new URL(origin).port;
let server,browser;
async function request(endpoint,body){
  const response=await fetch(origin+endpoint,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  assert(response.ok,`${endpoint}: ${response.status} ${await response.clone().text()}`);
  return response.json();
}
async function start(state){
  let occupied=false;try{await fetch(origin+'/healthz');occupied=true;}catch{}
  if(occupied)throw new Error('The isolated browser-test port is already in use: '+port);
  const python=process.env.STUDIO_PYTHON||path.join(studio,'.venv','Scripts','python.exe');
  server=spawn(python,['-m','uvicorn','studio.server:app','--host','127.0.0.1','--port',port],{
    cwd:studio,env:{...process.env,STUDIO_STATE_DIR:state,STUDIO_PASSWORD:'',PYTHONUTF8:'1'},windowsHide:true,stdio:['ignore','pipe','pipe']});
  let log='';server.stdout.on('data',chunk=>log+=chunk);server.stderr.on('data',chunk=>log+=chunk);
  for(let i=0;i<100;i++){
    if(server.exitCode!==null)throw new Error(log);
    try{await request('/healthz');return;}catch{}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw new Error('Server startup timed out: '+log);
}
async function stop(){
  if(server&&server.exitCode===null){
    // Windows venv python launches a child interpreter; stop this exact test tree.
    if(process.platform==='win32')await new Promise(resolve=>{const p=spawn('taskkill',['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});p.on('exit',resolve);});
    else {server.kill();await new Promise(resolve=>server.once('exit',resolve));}
  }
}
(async()=>{
  const artifacts=await fs.mkdtemp(path.join(studio,'runs','passport-browser-'));
  await start(artifacts);
  browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1366,height:1000},locale:'en-US',permissions:['clipboard-read','clipboard-write']});
  await context.addInitScript(()=>{
    localStorage.setItem('studio.settings',JSON.stringify({lang:'ko',garment:{fit:'slim'}}));
    window.__printCount=0;window.print=()=>window.__printCount++;
  });
  const page=await context.newPage(),errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
  const old='/c/xxxxxxxxxxxxxxxxxxx2AAADwAUEA';
  await page.goto(origin+old);await page.locator('#passport').waitFor({state:'visible'});
  assert.equal(new URL(page.url()).pathname,'/view/2AAADwAUEA');
  assert.equal(await page.locator('html').getAttribute('lang'),'ko');
  assert((await page.locator('#process-caption').textContent()).includes('연결된 공정 기록이 없습니다'));
  assert.equal(await page.locator('#timeline .unknown').count(),4);
  await page.screenshot({path:path.join(artifacts,'no-record.png'),fullPage:true});

  const example=await request('/api/simulation/example',{}),job=example.job_id;
  await request(`/api/jobs/${job}/size/override`,{size:'m',reason:'Browser verification'});
  const options=await request('/api/settings/options');
  const qrconfig={...options.default_config,colour:'forest_green'};
  async function generate(){return request(`/api/jobs/${job}/passport`,{config:qrconfig,base_url:origin});}
  let qr=await generate();
  await page.goto(origin+qr.url.replace(origin,''));await page.locator('#passport').waitFor({state:'visible'});
  assert.equal(await page.locator('#timeline .not_started').count(),3);
  assert(await page.locator('#metrics').isHidden());

  await request(`/api/jobs/${job}/run/simulate`,example.config);
  const simulation=await request(`/api/jobs/${job}/simulation`),plan=simulation.plan,run_id=simulation.state.run_id;
  const stitch=plan.operations.find(o=>o.kind==='stitch');
  await request(`/api/jobs/${job}/simulation/control`,{run_id,action:'seek',value:(stitch.start_s+stitch.end_s)/2});
  qr=await generate();
  await page.reload();await page.locator('#passport').waitFor({state:'visible'});
  assert.equal(await page.locator('#timeline .complete').count(),3);
  assert.equal(await page.locator('#timeline .in_progress').count(),1);
  const frozen=await request(`/api/passports/${qr.code}/summary`);
  await request(`/api/jobs/${job}/simulation/control`,{run_id,action:'seek',value:plan.totals.duration_s});
  assert.deepEqual(await request(`/api/passports/${qr.code}/summary`),frozen);
  qr=await generate();const completed=await request(`/api/passports/${qr.code}/summary`);
  assert.equal(completed.process.metrics.seams_complete,18);
  await page.reload();await page.locator('#passport').waitFor({state:'visible'});
  assert.equal(await page.locator('#timeline .complete').count(),4);

  for(const width of [360,1366]){
    await page.setViewportSize({width,height:1000});
    for(const [lang,title] of [['ko','폴로 셔츠'],['de','Poloshirt'],['en','Polo shirt']]){
      await page.locator(`[data-lang=${lang}]`).click();
      assert.equal(await page.locator('h1').textContent(),title);
      assert.equal(await page.locator('html').getAttribute('lang'),lang);
      assert.equal(await page.locator(`[data-lang=${lang}]`).getAttribute('aria-pressed'),'true');
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
      assert(!overflow,`Horizontal overflow: ${width}, ${lang}`);
      assert.equal(await page.locator('#time-note').textContent() === '',false);
      assert(await page.locator('.product-photo img').evaluate(img=>img.complete&&img.naturalWidth>0));
      await page.screenshot({path:path.join(artifacts,`${width}-${lang}.png`),fullPage:true});
    }
  }
  // Keyboard-only activation, with visible focus styling.
  await page.locator('[data-lang=en]').focus();await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.lang),'ko');
  assert.equal(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle),'solid');
  await page.keyboard.press('Enter');assert.equal(await page.locator('html').getAttribute('lang'),'ko');
  await page.locator('#copy-link').click();
  assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),origin+'/view/'+qr.code);
  const downloadPromise=page.waitForEvent('download');await page.locator('#download').click();
  const download=await downloadPromise;await download.saveAs(path.join(artifacts,'public-summary.json'));
  const saved=JSON.parse(await fs.readFile(path.join(artifacts,'public-summary.json'),'utf8'));
  assert.deepEqual(saved,completed);
  assert.equal(JSON.parse(await page.evaluate(()=>localStorage.getItem('studio.settings'))).garment.fit,'slim');
  await page.locator('#print').click();assert.equal(await page.evaluate(()=>window.__printCount),1);
  await page.emulateMedia({media:'print'});assert(await page.locator('.actions').isHidden());
  await page.pdf({path:path.join(artifacts,'passport-print.pdf'),format:'A4',printBackground:true});
  await page.emulateMedia({media:'screen'});
  assert(!requests.some(url=>/three|webgl|simulation[^/]*\.(js|css)|sewing-viewer|dppview/i.test(url)));
  assert.equal(errors.length,0,errors.join('\n'));

  // Loading, network failure, retry, and malformed codes.
  let unblock;const held=new Promise(resolve=>unblock=resolve);
  await page.route('**/api/passports/*/summary',async route=>{await held;await route.fulfill({status:503,body:'unavailable'});});
  await page.reload({waitUntil:'domcontentloaded'});
  assert(await page.locator('#page-state').isVisible());
  await page.screenshot({path:path.join(artifacts,'loading.png')});unblock();
  await page.locator('#retry').waitFor({state:'visible'});
  await page.screenshot({path:path.join(artifacts,'error.png')});
  await page.unroute('**/api/passports/*/summary');await page.locator('#retry').click();
  await page.locator('#passport').waitFor({state:'visible'});
  await page.goto(origin+'/view/not-valid');await page.locator('#retry').waitFor({state:'visible'});
  assert((await page.locator('#state-message').textContent()).includes('지원되는 제품 코드'));

  await require('./workflow-browser.cjs')({page:await context.newPage(),context,request,origin,job,artifacts,qr});
  await stop();await start(artifacts);
  assert.deepEqual(await request(`/api/passports/${qr.code}/summary`),completed);
  await page.goto(origin+'/view/'+qr.code);await page.locator('#passport').waitFor({state:'visible'});
  assert.equal(await page.locator('#timeline .complete').count(),4);
  console.log(JSON.stringify({passed:true,artifacts,code:qr.code,requests:[...new Set(requests.filter(u=>u.includes('/static/')))]},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();await stop();});
