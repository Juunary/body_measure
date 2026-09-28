import * as THREE from 'three';
import { CuttingViewer } from './simulation-viewer.js';
const ORDER=['zund','pfaff','overlock','button','qc'];
const SEWING=['pfaff','overlock'];
const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=x=>{x=clamp(x);return x*x*(3-2*x)};

// Presentation geometry is driven by the plan and Python's time, including seeks.
export class DesktopViewer extends CuttingViewer {
  constructor(canvas,onError){
    super(canvas,onError);
    this.scene.background.setHex(0xe8efec);
    this.scene.fog=new THREE.Fog(0xe8efec,15,32);
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure=1.15;
    this.controls.addEventListener('start',()=>{
      this.cameraTween=null;this.setAutoFollow(false);this.onManualCamera?.();
    });
    this.showLabels=true;
  }
  setPlan(plan){
    this.clearGarment();this.equipment.clear();
    this.makeMachines(plan.machines.filter(m=>ORDER.includes(m.id)));
    const layout={pfaff:[-3.5,0,-3.7],overlock:[-1.55,0,-3.7],button:[.4,0,-3.7],qc:[2.35,0,-3.7]};
    for(const [id,pos] of Object.entries(layout))this.equipment.get(id)?.position.set(...pos);
    super.setPlan(plan);
    this.previousMachine=null;
    this.makeGarment(plan);this.makeEffects();
    if(this.sewing){this.disposeGroup(this.sewing.assembly);this.sewing.assemblyTable.visible=false;this.sewing.assemblyLabel.visible=false}
    this.setLabels(this.showLabels);this.cameraMode('cutter');
  }
  outline(parent,points,color,height=.025){
    const shape=new THREE.Shape(points.map(p=>new THREE.Vector2(...p)));
    const geo=new THREE.ExtrudeGeometry(shape,{depth:.003,bevelEnabled:true,
      bevelSegments:3,steps:1,bevelSize:.002,bevelThickness:.001,curveSegments:24});
    geo.rotateX(Math.PI/2);
    const positions=geo.attributes.position;
    for(let i=0;i<positions.count;i++)positions.setY(i,positions.getY(i)+.008*Math.cos(positions.getX(i)*5)*Math.cos(positions.getZ(i)*4));
    geo.computeVertexNormals();
    const mesh=new THREE.Mesh(geo,new THREE.MeshStandardMaterial({
      color,roughness:.94,metalness:0,side:THREE.DoubleSide}));
    mesh.position.y=height;mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);
    return mesh;
  }
  makeGarment(plan){
    const front=plan.pieces.find(p=>p.id==='front'),w=front.width_mm/1000,h=front.height_mm/1000;
    this.garmentWidth=w;this.garmentLength=h;
    const g=this.garment=new THREE.Group();this.factory.add(g);
    const d=plan.config.design;this.components=[];
    const torso=front.contour.map(([x,y])=>[x/1000-w/2,y/1000-h/2]);
    this.components.push({mesh:this.outline(g,torso,0xc4ad7c),seams:['shoulder_left','shoulder_right']});
    const neckLine=front.seams.neckline;
    const neckZ=Math.max(...neckLine.map(p=>p[1]))/1000-h/2;
    const neckW=(Math.max(...neckLine.map(p=>p[0]))-Math.min(...neckLine.map(p=>p[0])))/2000;
    const shoulder=w*.39,sleeve=Math.min(.34,d.sleeve_length_mm/1000);
    for(const side of [-1,1]){
      const suffix=side===-1?'left':'right',x=side*shoulder;
      const pts=[[x,-h/2+.025],[side*(shoulder+sleeve*.9),-h/2+.16],
        [side*(shoulder+sleeve*.72),-h/2+.33],[side*w*.46,-h/2+.23]];
      this.components.push({mesh:this.outline(g,pts,0xc4ad7c,.018),
        seams:['armhole_'+suffix+'_front','armhole_'+suffix+'_back']});
      this.components.push({mesh:this.outline(g,[pts[1],pts[2],
        [pts[2][0]-side*.035,pts[2][1]-.015],[pts[1][0]-side*.035,pts[1][1]-.015]],0x55766a,.032),
        seams:['cuff_'+suffix]});
      this.components.push({mesh:this.outline(g,[[side*.008,neckZ-.002],[side*neckW,-h/2+.005],
        [side*(neckW+.033),-h/2+.039],[side*.043,neckZ+.062]],0x527567,.049),
        seams:['collar_front','collar_back']});
      this.line(g,[[side*.017,.058,neckZ],[side*.017,.058,neckZ+d.placket_length_mm/1000]],0x8c7858);
    }
    this.placketZ=neckZ;
    this.outline(g,[[-.018,neckZ],[.018,neckZ],[.018,neckZ+d.placket_length_mm/1000],
      [-.018,neckZ+d.placket_length_mm/1000]],0xb49a6b,.045);
    this.stitchLines=[];
    for(const [key,points] of Object.entries(front.seams)){
      if(!['hem','shoulder_left','shoulder_right','side_left','side_right'].includes(key))continue;
      const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points.map(([x,y])=>
        new THREE.Vector3(x/1000-w/2,.039,y/1000-h/2))),new THREE.LineDashedMaterial({
        color:0x607d65,dashSize:.004,gapSize:.002}));
      line.computeLineDistances();g.add(line);
      this.stitchLines.push({line,seam:key==='hem'?'hem_front':key});
    }
    this.buttonMeshes=[];this.holeMeshes=[];
    for(const b of plan.buttons){
      const z=neckZ+b.y_mm/1000,button=new THREE.Group();
      button.position.set(0,.060,z);g.add(button);
      this.cylinder(button,b.diameter_mm/2000,.006,[0,0,0],0xece6d7);
      for(const x of [-.0017,.0017])for(const zz of [-.0017,.0017])
        this.cylinder(button,.0007,.007,[x,.001,zz],0x4f574c);
      const hole=this.line(g,[[0,.056,z-b.hole_length_mm/2000],[0,.056,z+b.hole_length_mm/2000]],0x334e43);
      const border=new THREE.Mesh(new THREE.TorusGeometry(b.hole_length_mm/2000,.0008,5,24),this.material(0xe1cea6));
      border.rotation.x=Math.PI/2;border.scale.x=.22;border.position.set(0,.056,z);g.add(border);
      this.buttonMeshes.push(button);this.holeMeshes.push({hole,border});
    }
    g.visible=false;
  }
  makeEffects(){
    this.effects=new THREE.Group();this.factory.add(this.effects);this.statusLights=new Map();
    for(const id of SEWING){
      const p=this.equipment.get(id).position;
      this.box(this.effects,[1.5,.065,1.05],[p.x+1.25,.79,p.z+1.3],0xe7ecec);
      this.box(this.effects,[1.35,.006,.92],[p.x+1.25,.826,p.z+1.3],0xbed1c6);
      for(const x of [-.6,.6])for(const z of [-.4,.4])
        this.box(this.effects,[.045,.77,.045],[p.x+1.25+x,.39,p.z+1.3+z],0x334b46);
    }
    for(const id of ORDER){
      const p=this.equipment.get(id).position;
      this.statusLights.set(id,this.cylinder(this.effects,.038,.018,[p.x+.5,1.42,p.z],0x94a9a0));
    }
    const qc=this.equipment.get('qc').position;
    this.scan=this.box(this.effects,[1.22,.006,.012],[qc.x,.88,qc.z],0x2ce4bf);
    this.scan.material.emissive=new THREE.Color(0x21c99d);this.scan.visible=false;
    this.scanPlane=new THREE.Mesh(new THREE.PlaneGeometry(1.22,1),
      new THREE.MeshBasicMaterial({color:0x47d6b8,transparent:true,opacity:.09,side:THREE.DoubleSide,depthWrite:false}));
    this.scanPlane.rotation.x=-Math.PI/2;this.scanPlane.position.set(qc.x,.86,qc.z);this.effects.add(this.scanPlane);
    this.scanPlane.visible=false;
    this.buttonNeedle=this.cylinder(this.effects,.003,.12,[0,1.04,0],0x768c87);this.buttonNeedle.visible=false;
    this.ready=this.label(this.effects,'QC PASS / QR READY',[qc.x+.70,1.02,qc.z+.50],.58);this.ready.visible=false;
    this.box(this.effects,[1.35,.025,1.04],[qc.x,.80,qc.z],0x274f46);
  }
  setLabels(visible){
    this.showLabels=!!visible;
    const station=this.equipment.get(this.labelFocus);
    this.factory.traverse(o=>{
      if(!o.isSprite)return;
      let parent=o;while(parent&&parent!==station)parent=parent.parent;
      o.visible=!!visible&&(!station||!!parent);
    });
    if(this.sewing)this.sewing.assemblyLabel.visible=false;
    if(this.ready)this.ready.visible=!!visible&&!!this.state?.ready_for_qr;
  }
  poseAt(id,assembly=false){
    const station=this.equipment.get(id)||this.equipment.get('qc'),p=station.position.clone();
    if(assembly)return {position:p.add(new THREE.Vector3(1.25,.84,1.3)),angle:0};
    return {position:p.add(new THREE.Vector3(id==='button'?-.1:0,.845,id==='button'?.34:0)),angle:0};
  }
  apply(s){
    const follow=this.autoFollow;this.autoFollow=false;super.apply(s);this.autoFollow=follow;
    this.receivedAt=performance.now();
    const id=s.focus_machine_id||s.machine_id;
    if(follow&&id!==this.trackedMachine){this.focus(id);this.trackedMachine=id}
    this.renderPose(s,s.operation_progress,s.sim_time_s);
    for(const [mid,lamp] of this.statusLights||[]){
      const color=s.machines[mid]==='working'?0xf0aa55:s.machines[mid]==='complete'?0x35bb91:0x9eaea8;
      lamp.material.color.setHex(color);lamp.material.emissive.setHex(color);
      lamp.material.emissiveIntensity=s.machines[mid]==='working'?.4:0;
    }
  }
  renderPose(s,progress,time){
    if(!this.garment)return;
    const post=s.sewing_complete,during=s.stage==='sewing';
    this.garment.visible=post||during;
    if(this.sewing){this.sewing.assembly.visible=false;if(post)this.sewing.group.visible=false}
    let pose=this.poseAt(s.focus_machine_id||s.machine_id,during);
    if(s.transport&&s.transport.to!=='pfaff'){
      const from=this.poseAt(s.transport.from,SEWING.includes(s.transport.from));
      const to=this.poseAt(s.transport.to,SEWING.includes(s.transport.to));
      const f=smooth(progress);
      pose={position:from.position.lerp(to.position,f),angle:THREE.MathUtils.lerp(from.angle,to.angle,f)};
      pose.position.y+=Math.sin(f*Math.PI)*.22;
    }
    if(s.transport?.to==='pfaff')this.garment.visible=false;
    this.garment.position.copy(pose.position);this.garment.rotation.set(pose.angle,0,0);this.garment.scale.setScalar(1);
    const seams=s.sewing?.seams||{};
    for(const part of this.components){
      const assembled=post||part.seams.some(id=>['sewn','stitched'].includes(seams[id]));
      part.mesh.material.transparent=!assembled;part.mesh.material.opacity=assembled?1:.24;
      part.mesh.material.depthWrite=assembled;
    }
    for(const {line,seam} of this.stitchLines)line.visible=post||['sewn','stitched'].includes(seams[seam]);
    this.buttonMeshes.forEach((mesh,i)=>{
      const status=s.buttons?.[i];mesh.visible=['attaching','attached'].includes(status);
      mesh.position.y=.060+(status==='attaching'?(1-progress)*.06:0);
      const h=this.holeMeshes[i];h.border.visible=status!=='waiting';
      h.hole.visible=['buttonhole_cut','attaching','attached'].includes(status);
    });
    this.buttonNeedle.visible=s.machine_id==='button'&&s.operation.includes('stitch');
    if(this.buttonNeedle.visible){
      const index=this.plan.operations[s.operation_index].button_index;
      const local=new THREE.Vector3(0,.15,this.placketZ+this.plan.buttons[index].y_mm/1000);
      this.garment.updateMatrixWorld();this.buttonNeedle.position.copy(this.garment.localToWorld(local));
      this.buttonNeedle.position.y+=Math.sin(time*22)*.025;
    }
    this.scan.visible=s.operation==='qc_scan';this.scanPlane.visible=this.scan.visible;
    if(this.scan.visible)this.scan.position.z=this.equipment.get('qc').position.z-this.garmentLength/2+progress*this.garmentLength;
    this.ready.visible=this.showLabels&&!!s.ready_for_qr;
  }
  animateFrame(){
    if(this.cameraTween){
      const t=smooth((performance.now()-this.cameraTween.start)/650);
      this.camera.position.lerpVectors(this.cameraTween.from,this.cameraTween.to,t);
      this.controls.target.lerpVectors(this.cameraTween.fromTarget,this.cameraTween.target,t);
      if(t>=1)this.cameraTween=null;
    }
    const s=this.state;if(!s||!this.plan)return;
    const elapsed=s.status==='playing'?Math.min(.12,(performance.now()-this.receivedAt)/1000)*s.speed:0;
    const time=Math.min(s.operation_end_s||s.sim_time_s,s.sim_time_s+elapsed);
    const progress=clamp((time-s.operation_start_s)/(s.operation_end_s-s.operation_start_s));
    this.renderPose(s,Number.isFinite(progress)?progress:s.operation_progress,time);
    if(s.path_id!==null&&s.machine_id==='zund'){
      const path=this.plan.paths[s.path_id],p=Number.isFinite(progress)?progress:s.path_progress;
      const dist=path.distance_mm*p;let i=1;
      while(i<path.cumulative_mm.length-1&&path.cumulative_mm[i]<dist)i++;
      const a=path.points[i-1],b=path.points[i],f=(dist-path.cumulative_mm[i-1])/(path.cumulative_mm[i]-path.cumulative_mm[i-1]||1);
      this.head.position.x=(a[0]+(b[0]-a[0])*f)/1000-this.w/2;
      this.gantry.position.z=(a[1]+(b[1]-a[1])*f)/1000-this.l/2;
    }
  }
  moveCamera(position,target){
    if(!this.controls)return;
    this.cameraTween={from:this.camera.position.clone(),fromTarget:this.controls.target.clone(),
      to:position,target,start:performance.now()};
  }
  cameraMode(mode){
    if(!this.plan){super.cameraMode(mode);return}
    if(mode==='overview'){
      this.labelFocus=null;this.setLabels(this.showLabels);
      this.moveCamera(new THREE.Vector3(7.3,9.8,10),new THREE.Vector3(.5,.5,-1.8));
    }
    else if(mode==='top'){
      const p=this.equipment.get(this.state?.focus_machine_id||'zund')?.position||new THREE.Vector3();
      this.moveCamera(p.clone().add(new THREE.Vector3(0,4,.001)),p.clone().add(new THREE.Vector3(0,.8,0)));
    }else this.focus(mode==='detail'?(this.state?.focus_machine_id||'zund'):'zund',mode==='detail');
  }
  focus(id,close=false){
    const g=this.equipment.get(id);if(!g)return;
    this.labelFocus=id;this.setLabels(this.showLabels);
    const p=g.getWorldPosition(new THREE.Vector3());
    if(SEWING.includes(id)){
      const target=p.clone().add(new THREE.Vector3(close?-.22:.6,.86,close?0:.6));
      const offset=close?[.6,1.1,1.2]:[1.45,2.65,3.1];
      this.moveCamera(target.clone().add(new THREE.Vector3(...offset)),target);return;
    }
    const offset=id==='zund'?[2.6,3.6,3.6]:[1.05,2.25,2.2];
    this.moveCamera(p.clone().add(new THREE.Vector3(...offset)),p.clone().add(new THREE.Vector3(0,.78,.18)));
  }
  clearGarment(){
    for(const key of ['garment','effects']){
      if(this[key]){this.factory.remove(this[key]);this.disposeGroup(this[key]);this[key]=null}
    }
    this.trackedMachine=null;
  }
  clear(){this.clearGarment();super.clear()}
}
