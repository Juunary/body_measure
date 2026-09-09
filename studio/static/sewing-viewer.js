import * as THREE from 'three';

// Flat piece feed follows the paired local seam paths. This is kinematics;
// material folding and the assembly layout are explicitly schematic.
export class SewingViewer {
  constructor(viewer, station, plan) {
    this.viewer=viewer;this.station=station;this.plan=plan;
    this.group=new THREE.Group();station.add(this.group);
    this.feed=new THREE.Group();this.group.add(this.feed);
    this.assembly=new THREE.Group();this.group.add(this.assembly);
    this.pieces=new Map(plan.pieces.map(p=>[p.id,p]));this.active=null;
    viewer.box(this.group,[1.5,.07,1.05],[1.25,.75,1.3],0xe7ecec);
    viewer.label(this.group,'ASSEMBLY · SCHEMATIC',[1.25,.97,1.75],.8);
    this.assembled=new Map();
    this.pending=new Map();
    const positions={front:[1.25,.1],back:[1.25,.1],sleeve_left:[.84,-.08],sleeve_right:[1.66,-.08],
      collar:[1.25,-.24],cuff_left:[.70,.06],cuff_right:[1.80,.06],placket_left:[1.24,-.11],placket_right:[1.27,-.11]};
    plan.pieces.forEach((p,i)=>{
      const mesh=this.piece(p);const pos=positions[p.id];
      mesh.scale.setScalar(.7);mesh.position.set(pos[0]-p.width_mm*.00035,.801+i*.003,1.1+pos[1]-p.height_mm*.00035);
      this.assembly.add(mesh);this.assembled.set(p.id,mesh);
      const pending=this.piece(p);pending.position.set(-.55-p.width_mm/2000,.80+i*.003,.3-p.height_mm/2000);
      this.group.add(pending);this.pending.set(p.id,pending);
    });
  }
  piece(p){
    const shape=new THREE.Shape(p.contour.map(v=>new THREE.Vector2(v[0]/1000,v[1]/1000)));
    const geo=new THREE.ShapeGeometry(shape);geo.rotateX(Math.PI/2);
    const mat=this.viewer.material(p.material==='rib'?0x557f74:0xcbbb98);mat.side=THREE.DoubleSide;
    const mesh=new THREE.Mesh(geo,mat);mesh.receiveShadow=true;
    this.viewer.line(mesh,p.contour.map(v=>[v[0]/1000,.001,v[1]/1000]),0x617c72);
    return mesh;
  }
  sample(points,f){
    const lengths=[0];for(let i=1;i<points.length;i++)lengths.push(lengths[i-1]+Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]));
    const d=lengths.at(-1)*Math.max(0,Math.min(1,f));let i=1;while(i<lengths.length-1&&lengths[i]<d)i++;
    const a=points[i-1],b=points[i],r=(d-lengths[i-1])/(lengths[i]-lengths[i-1]||1);
    return {point:[a[0]+(b[0]-a[0])*r,a[1]+(b[1]-a[1])*r],angle:Math.atan2(b[0]-a[0],b[1]-a[1]),
      prefix:points.slice(0,i).concat([[a[0]+(b[0]-a[0])*r,a[1]+(b[1]-a[1])*r]])};
  }
  apply(s){
    this.state=s;this.receivedAt=performance.now();
    const sewing=s.sewing;if(!sewing)return;
    const inSewing=s.machine_id==='pfaff';this.group.visible=inSewing||s.sewing_complete;
    const seam=this.plan.sewing_seams.find(x=>x.id===sewing.seam_id);
    if(this.active!==seam?.id){
      this.viewer.disposeGroup(this.feed);this.layers=[];this.active=seam?.id;
      if(seam)seam.sides.forEach(side=>{
        const layer=new THREE.Group();this.feed.add(layer);
        layer.add(this.piece(this.pieces.get(side.piece_id)));
        this.viewer.line(layer,side.points.map(v=>[v[0]/1000,.002,v[1]/1000]),0x4b79ba);
        const stitched=this.viewer.line(layer,[[0,0,0],[0,0,0]],0xf07830);
        this.layers.push({layer,side,stitched});
      });
    }
    this.feed.visible=!!seam&&inSewing;
    (this.layers||[]).forEach(({layer,side,stitched},i)=>{
      const p=this.sample(side.points,sewing.seam_progress);const angle=-p.angle;
      // Rotate the local tangent towards feed Z and hold the current stitch
      // point exactly under the fixed needle at X=-.22, Z=0.
      layer.rotation.y=angle;
      const x=p.point[0]/1000,z=p.point[1]/1000;
      layer.position.set(-.22-Math.cos(angle)*x-Math.sin(angle)*z,.869+i*.004,Math.sin(angle)*x-Math.cos(angle)*z);
      stitched.geometry.dispose();stitched.geometry=new THREE.BufferGeometry().setFromPoints(p.prefix.map(v=>new THREE.Vector3(v[0]/1000,.004,v[1]/1000)));
      stitched.visible=sewing.seam_progress>0;
    });
    for(const [id,mesh] of this.assembled)mesh.visible=s.pieces[id]==='sewn'&&!(seam?.piece_ids.includes(id)&&inSewing);
    for(const [id,mesh] of this.pending)mesh.visible=s.pieces[id]!=='sewn'&&!(seam?.piece_ids.includes(id))&&s.operation!=='transfer_to_sewing';
    this.animate();
  }
  animate(){
    const s=this.state;if(!s)return;
    const sewing=s.sewing;
    const machine=this.plan.config.machine;
    const elapsed=s.status==='playing'?Math.min(.1,(performance.now()-this.receivedAt)/1000)*s.speed:0;
    const phase=(s.sim_time_s+elapsed)*machine.stitches_per_min/60*Math.PI*2;
    if(this.viewer.sewingNeedle)this.viewer.sewingNeedle.position.y=.933+(s.operation==='stitch'?Math.sin(phase)*.02:.025);
    if(this.viewer.sewingFoot)this.viewer.sewingFoot.position.y=sewing.presser_down?.883:.912;
    if(this.viewer.sewingWheel)this.viewer.sewingWheel.rotation.x=s.operation==='stitch'?phase:0;
  }
  dispose(){this.station.remove(this.group);this.viewer.disposeGroup(this.group);}
}
