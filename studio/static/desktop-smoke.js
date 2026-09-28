(async()=>{
  const $=id=>document.getElementById(id),checks=[];
  const assert=(condition,message)=>{if(!condition)throw new Error(message)};
  const wait=async(predicate,label)=>{
    const end=performance.now()+10000;
    while(!predicate()){
      if(performance.now()>end)throw new Error('Timed out: '+label+'; '+$('error').textContent);
      await new Promise(r=>setTimeout(r,50));
    }
  };
  try{
    const ui=await import('./desktop.js');
    await wait(()=>window.pywebview&&$('process-inputs').children.length,'bridge ready');
    assert(ui.viewer&&!ui.viewer.renderer.getContext().isContextLost(),'WebGL context');
    const errors=[];window.addEventListener('error',e=>errors.push(e.message));
    window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
    $('example').click();await wait(()=>ui.plan&&ui.lastState,'example');
    await window.pywebview.api.control('pause');
    await wait(()=>ui.lastState.status==='paused','pause');
    assert(ui.viewer.equipment.size===5,'All five machines render');
    const seek=async(time)=>{
      const old=ui.lastState.revision;
      $('seek').value=time;const target=Number($('seek').value);$('seek').dispatchEvent(new Event('change'));
      await wait(()=>ui.lastState.revision>old&&Math.abs(ui.lastState.sim_time_s-target)<.001,'seek '+target);
      assert(ui.viewer.state.seq===ui.lastState.seq,'3D uses current Python state');
      assert($('terminal-output').textContent===ui.lastState.terminal_lines.join('\n'),'terminal state matches');
      assert(!$('error').textContent,$('error').textContent);
    };
    for(const chapter of ui.plan.timeline){
      const operations=ui.plan.operations.filter(op=>op.start_s>=chapter.start_s&&op.start_s<chapter.end_s);
      const op=operations.find(op=>['stitch','button_attach_stitch','qc_scan','cut_outer','ready_for_qr'].includes(op.kind))||operations[0];
      await seek((op.start_s+op.end_s)/2);
      assert(ui.lastState.chapter===chapter.id,'Chapter '+chapter.id);
      assert(document.querySelector('[aria-current="step"]').dataset.chapter===chapter.id,'Chapter selection');
      if(chapter.id==='sewing')assert(ui.lastState.step&&$('operation').textContent.startsWith(String(ui.lastState.step.no).padStart(2,'0')),'Work step shown');
      if(chapter.id==='qc')assert(ui.viewer.scan.visible,'QC scan renders');
      checks.push(chapter.id);
    }
    assert(!$('ready-card').hidden&&ui.viewer.garment.visible,'Finished garment and readiness');
    assert(ui.viewer.buttonMeshes.filter(b=>b.visible).length===2,'Two finished buttons');
    await seek(0);
    assert($('ready-card').hidden&&!ui.viewer.garment.visible,'Rewind removes ready garment');
    assert(ui.viewer.buttonMeshes.every(b=>!b.visible),'Rewind removes buttons');
    $('speed').value='0.1';$('speed').dispatchEvent(new Event('change'));
    await wait(()=>ui.lastState.speed===.1,'0.1 speed');
    for(const language of ['en','de','ko']){
      $('language').value=language;$('language').dispatchEvent(new Event('change'));
      assert(document.documentElement.lang===language,'Language '+language);
      assert($('stage-track').children.length===5,'Localized chapters');
    }
    assert(errors.length===0,errors.join('\n'));
    return {ok:true,chapters:checks,webgl:true,rewind:true,terminal_sync:true,languages:3};
  }catch(e){return {ok:false,error:e.stack||String(e),checks}}
})()
