const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs/promises');
const {spawn}=require('node:child_process');
module.exports=async function({page,context,request,origin,job,artifacts,qr}){
  const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
  async function until(check,message){for(let i=0;i<600;i++){if(await check())return;await new Promise(r=>setTimeout(r,100));}throw new Error(message+'\n'+errors.join('\n'));}
  const base=`/api/jobs/${job}`;
  await page.goto(origin+'/measure?job='+job);
  await until(async()=>await page.locator('#workflow-status').textContent().then(s=>s.includes(job)),'Measure did not restore job');
  assert.equal(await page.locator('#viewer').count(),1);assert.equal(await page.locator('#cutting-canvas').count(),0);assert.equal(await page.locator('#qr-card').count(),0);
  assert.equal(await page.locator('html').getAttribute('lang'),'ko');
  await page.locator('#btn-settings').click();assert(await page.locator('#garment-form').isVisible());
  await page.locator('#btn-drawer-close').click();
  const mark=requests.length;
  await page.locator('[data-page=simulation]').click();
  await until(async()=>!(await page.locator('[data-control=play]').isDisabled()),'Simulation controls unavailable');
  assert.equal(await page.locator('#viewer').count(),0);assert.equal(await page.locator('#cutting-canvas').count(),1);
  assert(!requests.slice(mark).some(r=>/\/viewer\.js/.test(r.url)));
  let sim=await request(base+'/simulation'),run=sim.state.run_id;
  const cut=sim.plan.operations.find(o=>o.kind==='cut_outer');
  await request(base+'/simulation/control',{run_id:run,action:'seek',value:cut.start_s});
  await page.locator('#sim-speed').selectOption('0.1');await page.locator('[data-control=play]').click();
  await page.locator('[data-page=qr]').focus();
  const focusTime=(await request(base+'/simulation')).state.sim_time_s;
  await until(async()=>(await request(base+'/simulation')).state.sim_time_s>focusTime+.03,'Server clock did not advance');
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.page),'qr','Live updates moved keyboard focus');
  const before=await request(base+'/simulation');
  const start=requests.length;
  await page.locator('[data-page=qr]').click();
  await until(async()=>!(await page.locator('#qr-generate').isDisabled()),'QR generation unavailable');
  assert.equal(await page.locator('canvas').count(),0);
  assert(!requests.slice(start).some(r=>/three|\/viewer\.js|simulation-viewer|sewing-viewer/.test(r.url)));
  const later=await request(base+'/simulation');assert.equal(later.state.run_id,run);assert(later.state.sim_time_s>before.state.sim_time_s);
  await page.reload();await until(async()=>!(await page.locator('#qr-generate').isDisabled()),'QR reload failed');
  assert.equal((await request(base+'/simulation')).state.run_id,run);
  await page.goBack();await until(async()=>await page.locator('#cutting-canvas').count()>0,'Back navigation failed');
  await until(async()=>!(await page.locator('[data-control=pause]').isDisabled()),'Live simulation did not restore');
  await page.locator('[data-control=pause]').click();
  await until(async()=>(await request(base+'/simulation')).state.status==='paused','Pause failed');
  assert.equal((await request(base+'/simulation')).state.run_id,run);
  assert(!requests.some(r=>r.method==='POST'&&r.url.endsWith('/run/simulate')),'Navigation restarted the simulation');
  await page.locator('#sim-inputs > summary').click();
  await page.locator('[data-config-key=electricity_eur_kwh]').fill('0.5');
  await page.locator('#sim-start').click();
  await until(async()=>(await request(base+'/simulation')).state.run_id!==run,'New preset did not start a new run');
  sim=await request(base+'/simulation');run=sim.state.run_id;
  assert.equal(sim.plan.config.resources.electricity_eur_kwh,.5);
  await request(base+'/simulation/control',{run_id:run,action:'seek',value:sim.plan.totals.duration_s});
  // Attach the real CLI to a paused web run, then consume its next SSE state.
  const cutting=sim.plan.operations.find(o=>o.kind==='cut_outer');
  await request(base+'/simulation/control',{run_id:run,action:'seek',value:cutting.start_s});
  const attachedInitial=(await request(base+'/simulation')).state;
  const logPath=path.join(artifacts,'attached-cli.jsonl'),studio=path.resolve(__dirname,'..');
  const cli=spawn(process.env.STUDIO_PYTHON||path.join(studio,'.venv','Scripts','python.exe'),
    ['-m','studio.simulate','--attach',job,'--server',origin,'--no-color','--jsonl',logPath],
    {cwd:studio,env:{...process.env,PYTHONUTF8:'1',STUDIO_PASSWORD:''},windowsHide:true,stdio:['ignore','pipe','pipe']});
  let output='';cli.stdout.on('data',chunk=>output+=chunk);cli.stderr.on('data',chunk=>output+=chunk);
  const exited=new Promise((resolve,reject)=>{cli.on('exit',code=>resolve(code));cli.on('error',reject);});
  try{
    await until(async()=>{try{return (await fs.readFile(logPath,'utf8')).includes('\n');}catch{return false;}},'Attached CLI did not receive initial state');
    const first=JSON.parse((await fs.readFile(logPath,'utf8')).trim().split('\n')[0]);
    assert.deepEqual(first.resources,attachedInitial.resources);assert.deepEqual(first.size,attachedInitial.size);
    await request(base+'/simulation/control',{run_id:run,action:'seek',value:sim.plan.totals.duration_s});
    await until(async()=>cli.exitCode!==null,'Attached CLI did not receive completion');
    assert.equal(await exited,0,output);
    const states=(await fs.readFile(logPath,'utf8')).trim().split('\n').map(JSON.parse);
    assert(states.length>=2);assert(states.at(-1).finished);assert(!output.includes('\u001b['));
    assert.deepEqual(states.at(-1).resources,(await request(base+'/simulation')).state.resources);
  }finally{if(cli.exitCode===null)cli.kill();}
  await until(async()=>(await page.locator('#sim-resource-card').textContent()).includes('EUR'),'Resources missing');
  for(const width of [360,1366]){
    await page.setViewportSize({width,height:1000});
    for(const lang of ['ko','de','en']){
      await page.locator(`#langs [data-lang=${lang}]`).click();
      assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),`Simulation overflow ${width} ${lang}`);
      await page.screenshot({path:path.join(artifacts,`simulation-${width}-${lang}.png`),fullPage:true});
    }
  }
  // A second tab sees the same authoritative clock, without starting a job.
  const second=await context.newPage();second.on('pageerror',e=>errors.push(e.message));
  // Hold an old reconnect snapshot until after the newer size SSE event.
  let releaseOld,resultReads=0,oldCaptured=false,newReadFinished=false;
  const oldGate=new Promise(resolve=>releaseOld=resolve);
  await second.route('**'+base+'/result',async route=>{
    const read=++resultReads;
    if(read===1){await route.continue();return;}
    const response=await route.fetch();
    if(read===2){oldCaptured=true;await oldGate;}
    await route.fulfill({response});if(read>=3)newReadFinished=true;
  });
  await second.goto(origin+'/qr?job='+job);await until(async()=>!(await second.locator('#qr-generate').isDisabled()),'Second tab did not restore');
  await until(async()=>oldCaptured,'Reconnect snapshot was not requested');
  assert((await second.locator('#workflow-status').textContent()).includes('연구용 봉제 완료'));
  await request(base+'/size/override',{size:'l',reason:'Browser mismatch test'});
  try{await until(async()=>await second.locator('#qr-generate').isDisabled(),'Size mismatch did not disable generation');}
  catch(e){
    await second.screenshot({path:path.join(artifacts,'mismatch-failure.png'),fullPage:true});
    console.error(JSON.stringify({ui:await second.locator('body').innerText(),result:await request(base+'/result'),simulation:(await request(base+'/simulation')).state},null,2));throw e;
  }
  assert((await second.locator('#qr-message').textContent()).includes('사이즈'));
  releaseOld();await until(async()=>newReadFinished,'Stale snapshot was not refreshed after the size event');
  await second.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert(await second.locator('#qr-generate').isDisabled(),'Old reconnect snapshot restored an invalid size');
  await second.unroute('**'+base+'/result');
  await request(base+'/size/override',{size:'m',reason:'Restore test size'});
  await until(async()=>!(await second.locator('#qr-generate').isDisabled()),'Restored size remains blocked');
  // A different colour keeps the earlier persistence test's QR record untouched.
  await second.locator('.swatches button').nth(4).click();
  await second.locator('#qr-generate').click();await second.locator('#qr-card details summary').waitFor({state:'visible'});
  await until(async()=>!(await second.locator('#qr-generate').isDisabled()),'QR cannot be regenerated after capture');
  await second.locator('#qr-card details summary').click();
  const document=JSON.parse(await second.locator('#qr-card pre').textContent());
  assert(document.manufacturing_data.resources.cost_eur>0);assert.equal(document.manufacturing_data.size.label,'M');
  assert(!document.production_events&&!document.manufacturing_date);
  const record=await request(base+'/result');const code=record.passport.code;assert.notEqual(code,qr.code);
  const saved=await request('/api/passports/'+code+'/summary');assert.deepEqual(saved.process.resources,document.manufacturing_data.resources);
  for(const width of [360,1366]){
    await second.setViewportSize({width,height:1000});
    for(const lang of ['ko','de','en']){
      await second.locator(`#langs [data-lang=${lang}]`).click();
      await until(async()=>await second.locator('html').getAttribute('lang')===lang,'Language failed');
      assert(!(await second.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),`QR overflow ${width} ${lang}`);
      await second.screenshot({path:path.join(artifacts,`qr-${width}-${lang}.png`),fullPage:true});
    }
  }
  await second.goto(origin+'/view/'+code);await second.locator('#passport').waitFor({state:'visible'});
  await second.locator('.public-json summary').click();
  assert.deepEqual(JSON.parse(await second.locator('#public-json').textContent()),saved);
  assert((await second.locator('#public-resource-card').textContent()).includes('CO₂e'));
  await second.goto(origin+'/simulation?job=missing-job');
  await until(async()=>(await second.locator('#workflow-message').textContent()).includes('만료'),'Missing-job state absent');
  assert(await second.locator('#sim-start').isDisabled());assert(!(await second.locator('#sim-example').isDisabled()));
  // Exercise the original measurement UI against a real synthetic mesh.
  const files=await request('/api/files');const scan=files.find(f=>f.id==='generated:smpl_neutral0_apose');
  assert(scan,'Synthetic validation mesh missing');
  const created=await request('/api/jobs',{file_id:scan.id,unit:'m',up_axis:'Y',population:'men'});
  await second.goto(origin+'/measure?job='+created.job_id);
  await until(async()=>!(await second.locator('#btn-load').isDisabled()),'Load button unavailable');
  await second.locator('#btn-load').click();
  await until(async()=>!(await second.locator('#btn-measure').isDisabled()),'Mesh did not load');
  const measuredJob=new URL(second.url()).searchParams.get('job');
  await second.locator('#btn-measure').click();
  await until(async()=>{const d=await request(`/api/jobs/${measuredJob}/result`);return !d.busy_stage&&d.measurements.length===7;},'Measurement did not complete');
  await until(async()=>!(await second.locator('#btn-size').isDisabled()),'Size button unavailable after measurement');
  await second.locator('#btn-size').click();
  await until(async()=>!(await request(`/api/jobs/${measuredJob}/result`)).busy_stage,'Size assignment did not complete');
  for(const width of [360,1366]){
    await second.setViewportSize({width,height:1000});
    for(const lang of ['ko','de','en']){
      await second.locator(`#langs [data-lang=${lang}]`).click();
      await until(async()=>await second.locator('html').getAttribute('lang')===lang,'Measurement language failed');
      assert(!(await second.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),`Measure overflow ${width} ${lang}`);
      await second.screenshot({path:path.join(artifacts,`measure-${width}-${lang}.png`),fullPage:true});
    }
  }
  await second.reload();await until(async()=>!(await second.locator('#btn-measure').isDisabled()),'Measured job did not reload');
  assert.equal(new URL(second.url()).searchParams.get('job'),measuredJob);
  const names=(await request(`/api/jobs/${measuredJob}/result`)).measurements.map(m=>m.name);
  assert.equal(names.length,7);
  await second.close();
  assert.deepEqual(errors,[]);await page.close();
};
