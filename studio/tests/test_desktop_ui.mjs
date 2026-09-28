import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../static/desktop-state.js',import.meta.url),'utf8');
const {ResponseGate,chaptersFor,duration}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
test('responses from replaced runs and obsolete seeks are rejected',()=>{
  const gate=new ResponseGate(),first={run_id:'a',plan_id:'p',seq:1,revision:0};
  gate.reset(first);assert.equal(gate.accept(first),true);
  assert.equal(gate.accept({...first,seq:5,revision:1}),true);
  assert.equal(gate.accept({...first,seq:4}),false);
  assert.equal(gate.accept({...first,seq:6,revision:0}),false);
  gate.reset({...first,run_id:'b'});
  assert.equal(gate.accept({...first,seq:900}),false);
  assert.equal(gate.accept({...first,run_id:'b'}),true);
  gate.reset();assert.equal(gate.accept(first),false);
});
test('legacy projects receive all eight chapters with transport included',()=>{
  const mids=['pfaff','overlock','coverstitch','button','veit','qc'];
  const p={operations:mids.map((id,i)=>({kind:'transfer_to_'+id,start_s:(i+1)*10})),
    boundaries:{qc_end_s:70},totals:{duration_s:70.01}};
  const chapters=chaptersFor(p);
  assert.equal(chapters.length,8);assert.equal(chapters[2].machine_id,'overlock');
  assert.equal(chapters[0].start_s,0);assert.equal(chapters.at(-1).end_s,70.01);
  for(let i=1;i<chapters.length;i++)assert.equal(chapters[i-1].end_s,chapters[i].start_s);
});
test('floating point schedule boundaries format without losing a second',()=>{
  assert.equal(duration(304.9999999999),'5:05');assert.equal(duration(69.3),'1:09');
});
