import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SewingViewer } from './sewing-viewer.js';

const palette={metal:0xc5d0d4,dark:0x243942,body:0xe7ecec,accent:0x168577,cut:0xd98437,done:0x40b79f};
export class CuttingViewer {
  constructor(canvas,onError) {
    this.canvas=canvas;this.plan=null;this.state=null;this.objects=new Map();this.paths=new Map();this.tags=[];
    this.scene=new THREE.Scene();this.scene.background=new THREE.Color(0xeaf0ef);
    this.camera=new THREE.PerspectiveCamera(40,1,.01,100);this.camera.position.set(4.4,4.5,5.8);
    this.renderer=new THREE.WebGLRenderer({canvas,antialias:true});this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;
    this.controls=new OrbitControls(this.camera,canvas);this.controls.target.set(0,.7,0);this.controls.enableDamping=true;
    this.controls.minDistance=.4;this.controls.maxDistance=20;this.controls.maxPolarAngle=Math.PI*.49;
    this.scene.add(new THREE.HemisphereLight(0xffffff,0x63756c,2.4));
    const sun=new THREE.DirectionalLight(0xffffff,3.2);sun.position.set(2,8,5);sun.castShadow=true;
    sun.shadow.mapSize.set(2048,2048);Object.assign(sun.shadow.camera,{left:-9,right:9,top:9,bottom:-9});sun.shadow.bias=-.0003;this.scene.add(sun);
    this.box(this.scene,[17,.08,12],[0,-.08,-2],0xd8e3df).receiveShadow=true;
    const grid=new THREE.GridHelper(16,32,0xb2c8bd,0xcbdad2);grid.position.y=-.035;this.scene.add(grid);
    this.factory=new THREE.Group();this.scene.add(this.factory);this.dynamic=new THREE.Group();this.scene.add(this.dynamic);
    this.equipment=new Map();this.makeCutter(1.6,2);this.cameraMode('cutter');
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(canvas.parentElement);
    canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();onError();});
    this.renderer.setAnimationLoop(()=>{
      if(!canvas.clientWidth||!canvas.clientHeight)return;
      if(this.targetHead){this.head.position.x+=(this.targetHead[0]-this.head.position.x)*.35;this.gantry.position.z+=(this.targetHead[1]-this.gantry.position.z)*.35;}
      this.sewing?.animate();
      this.controls.update();this.renderer.render(this.scene,this.camera);
    });
  }
  material(color){return new THREE.MeshStandardMaterial({color,roughness:.65,metalness:color===palette.metal?.45:.08});}
  box(parent,size,pos,color){const mesh=new THREE.Mesh(new THREE.BoxGeometry(...size),this.material(color));mesh.position.set(...pos);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;}
  cylinder(parent,radius,length,pos,color,axis='y'){
    const mesh=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,length,24),this.material(color));mesh.position.set(...pos);
    if(axis==='x')mesh.rotation.z=Math.PI/2;if(axis==='z')mesh.rotation.x=Math.PI/2;mesh.castShadow=true;parent.add(mesh);return mesh;
  }
  line(parent,points,color){const geo=new THREE.BufferGeometry().setFromPoints(points.map(p=>new THREE.Vector3(...p)));
    const obj=new THREE.Line(geo,new THREE.LineBasicMaterial({color}));parent.add(obj);return obj;}
  label(parent,text,pos,width=1.5){
    const c=document.createElement('canvas');c.width=768;c.height=128;const ctx=c.getContext('2d');
    ctx.fillStyle='#f6faf8';ctx.fillRect(0,0,768,128);ctx.fillStyle='#163f3b';ctx.font='600 48px sans-serif';ctx.textAlign='center';ctx.fillText(text,384,80);
    const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;
    const obj=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false}));obj.position.set(...pos);obj.scale.set(width,width/6,1);parent.add(obj);return obj;
  }
  disposeGroup(group){group.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material]){m.map?.dispose();m.dispose();}}});group.clear();}
  makeCutter(w,l){
    if(this.cutter){this.factory.remove(this.cutter);this.disposeGroup(this.cutter);}
    this.w=w;this.l=l;const g=this.cutter=new THREE.Group();this.factory.add(g);this.equipment.set('zund',g);
    this.box(g,[w+.22,.22,l+.2],[0,.65,0],palette.body);
    this.box(g,[w+.08,.08,l+.06],[0,.8,0],palette.dark);
    this.box(g,[w,.018,l],[0,.848,0],0x4f7069);
    for(const x of [-w/2,w/2])for(const z of [-l/2,l/2]){this.box(g,[.09,.62,.09],[x,.3,z],palette.dark);this.cylinder(g,.07,.05,[x,.035,z],0x53656a);}
    for(const x of [-w/2-.06,w/2+.06])this.box(g,[.07,.05,l+.22],[x,.89,0],palette.metal);
    this.gantry=new THREE.Group();g.add(this.gantry);this.box(this.gantry,[w+.28,.14,.11],[0,1.02,0],palette.metal);
    for(const x of [-w/2-.1,w/2+.1])this.box(this.gantry,[.12,.19,.24],[x,.965,0],palette.body);
    this.head=new THREE.Group();this.gantry.add(this.head);this.box(this.head,[.16,.18,.16],[0,1.02,.01],palette.body);
    this.box(this.head,[.11,.07,.03],[0,1.04,.1],palette.dark);this.cylinder(this.head,.018,.06,[0,.915,0],0x586369);
    this.blade=this.cylinder(this.head,.028,.008,[0,.891,0],palette.metal,'x');
    this.light=this.cylinder(this.head,.015,.025,[.055,1.15,0],0x4ed8a5);
    this.roll=this.cylinder(g,.16,w,[0,.9,-l/2-.33],0xb2c6b7,'x');
    this.cylinder(g,.024,w+.3,[0,.9,-l/2-.33],palette.metal,'x');
    for(const x of [-w/2-.1,w/2+.1])this.box(g,[.07,.9,.12],[x,.45,-l/2-.33],palette.dark);
    this.box(g,[.28,.13,.3],[w/2+.32,.76,-.5],palette.dark);
    const screen=this.box(g,[.29,.23,.045],[w/2+.32,1.02,-.54],0x253a40);screen.rotation.x=-.2;
    this.box(g,[.23,.15,.008],[w/2+.32,1.03,-.51],0x489a90);
    this.box(g,[.88,.1,1.1],[w/2+.75,.65,.45],palette.body);
    this.label(g,'ZÜND S3 · ROTARY CUTTER',[0,1.45,-l/2-.25],1.8);
    this.label(g,'CUT PARTS',[w/2+.75,.9,1.08],.65);
    this.head.position.x=-w/2;this.gantry.position.z=-l/2;
  }
  table(g){this.box(g,[1.1,.07,.7],[0,.75,0],palette.body);for(const x of [-.43,.43])for(const z of [-.25,.25])this.box(g,[.045,.73,.045],[x,.36,z],palette.dark);}
  makeMachines(catalogue){
    if(this.other){this.factory.remove(this.other);this.disposeGroup(this.other);}
    this.other=new THREE.Group();this.factory.add(this.other);
    catalogue.filter(m=>m.id!=='zund').forEach((m,i)=>{
      const g=new THREE.Group();g.position.set(-4.15+(i%6)*1.65,0,-3.0-Math.floor(i/6)*2.35);this.other.add(g);this.equipment.set(m.id,g);
      if(m.shape==='sewing'||m.shape==='embroidery'){
        this.table(g);this.box(g,[.52,.07,.28],[0,.83,0],palette.dark);
        this.box(g,[.13,.34,.22],[.2,1,0],palette.body);this.box(g,[.52,.12,.23],[0,1.13,0],palette.body);
        this.box(g,[.11,.2,.16],[-.22,1.02,0],palette.body);this.cylinder(g,.06,.08,[.32,1.12,0],palette.dark,'x');
        const needle=this.cylinder(g,.006,.1,[-.22,.87,0],palette.metal);
        if(m.id==='pfaff'){
          this.sewingNeedle=needle;
          this.sewingFoot=this.box(g,[.045,.008,.04],[-.22,.837,0],palette.metal);
          this.sewingWheel=this.cylinder(g,.065,.015,[.37,1.12,0],0x7d958c,'x');
          this.box(this.sewingWheel,[.02,.10,.015],[0,0,0],palette.metal);
        }
        this.box(g,[.23,.015,.24],[-.19,.798,.02],0x96b8b0);
        for(let j=0;j<(m.shape==='embroidery'?4:m.id==='overlock'?3:2);j++)this.cylinder(g,.02,.085,[.02+j*.07,1.27,-.07],j%2?0xcb9c65:0x507e74);
        this.line(g,[[.07,1.31,-.07],[-.19,1.24,0],[-.22,.84,0]],0x73847c);
        this.box(g,[.18,.025,.18],[0,.08,.2],palette.dark);
        if(m.shape==='embroidery'){const ring=new THREE.Mesh(new THREE.TorusGeometry(.11,.01,6,32),this.material(palette.metal));ring.rotation.x=Math.PI/2;ring.position.set(-.19,.82,.05);g.add(ring);}
      } else if(m.shape==='laser'){
        this.box(g,[1.35,.7,.92],[0,.4,0],palette.body);this.box(g,[1.15,.04,.72],[0,.78,0],palette.dark);
        const lid=this.box(g,[1.28,.055,.82],[0,1.1,-.2],0x629189);lid.rotation.x=-.58;
        this.box(g,[1.1,.065,.065],[0,.87,0],palette.metal);this.box(g,[.08,.13,.08],[.15,.82,0],0xb17945);
      } else if(m.shape==='finisher'){
        this.box(g,[.6,.36,.55],[0,.2,0],palette.body);this.cylinder(g,.045,.7,[0,.62,0],palette.metal);
        const form=new THREE.Mesh(new THREE.CylinderGeometry(.15,.24,.7,8),this.material(0xabb9b2));form.position.y=.92;g.add(form);
        this.cylinder(g,.09,.12,[0,1.31,0],palette.body);this.box(g,[.85,.08,.1],[0,1.19,0],palette.metal);
        for(const x of [-.42,.42])this.box(g,[.055,.65,.055],[x,.89,0],palette.dark);
      } else if(m.shape==='camera'){
        this.table(g);this.box(g,[.055,.9,.055],[0,1.17,-.25],palette.metal);this.box(g,[.05,.05,.48],[0,1.6,-.04],palette.metal);
        this.box(g,[.18,.12,.16],[0,1.55,.17],palette.dark);this.cylinder(g,.035,.06,[0,1.46,.17],0x4b8096);
        this.box(g,[.8,.015,.5],[0,.798,0],0xe2eccc);
      } else if(m.shape==='printer'){
        this.box(g,[1.1,.65,.72],[0,.43,0],palette.body);this.box(g,[1.05,.18,.68],[0,.85,-.06],palette.dark);
        this.box(g,[.5,.035,.66],[0,.77,.38],palette.metal);this.box(g,[.34,.018,.43],[0,.795,.4],0x92bab1);
        this.box(g,[.18,.15,.025],[.38,1,.32],0x408d7c);
      } else {this.table(g);for(let j=0;j<3;j++)this.cylinder(g,.10,.75,[0,.92+j*.22,0],j%2?0xc5ba9a:0x6d9d8c,'x');}
      this.label(g,m.name,[0,1.8,0],1.25);
      this.box(g,[1.45,.01,1.05],[0,-.02,0],m.source==='plan'?0xc0d4cd:0xd0cbbb);
    });
  }
  setPlan(plan){
    this.sewing?.dispose();this.sewing=null;
    this.plan=plan;this.disposeGroup(this.dynamic);this.objects.clear();this.paths.clear();
    this.makeCutter(plan.config.machine.bed_width_mm/1000,plan.config.machine.bed_length_mm/1000);
    this.cloth=this.box(this.dynamic,[1,.002,1],[0,.865,0],0xd7c9a5);
    this.scraps=new Map();this.targetHead=null;
    for(const win of plan.windows){
      const outline=new THREE.Shape([new THREE.Vector2(0,0),new THREE.Vector2(win.width_mm/1000,0),new THREE.Vector2(win.width_mm/1000,win.length_mm/1000),new THREE.Vector2(0,win.length_mm/1000)]);
      for(const p of win.placements)outline.holes.push(new THREE.Path(p.contour.map(v=>new THREE.Vector2(v[0]/1000,v[1]/1000))));
      const geo=new THREE.ShapeGeometry(outline);geo.rotateX(Math.PI/2);
      const material=this.material(win.material==='rib'?0x8ba393:0xd7c9a5);material.side=THREE.DoubleSide;
      const scrap=new THREE.Mesh(geo,material);scrap.position.set(-this.w/2,.863,-this.l/2);scrap.receiveShadow=true;scrap.visible=false;
      this.dynamic.add(scrap);this.scraps.set(win.id,scrap);
    }
    for(const win of plan.windows)for(const p of win.placements){
      const shape=new THREE.Shape(p.contour.map(v=>new THREE.Vector2(v[0]/1000,v[1]/1000)));
      const geo=new THREE.ShapeGeometry(shape);geo.rotateX(Math.PI/2);
      const mat=this.material(win.material==='rib'?0x859e8e:0xcbbb98);mat.side=THREE.DoubleSide;
      const mesh=new THREE.Mesh(geo,mat);mesh.receiveShadow=true;this.dynamic.add(mesh);
      const edge=this.line(mesh,p.contour.map(v=>[v[0]/1000,.001,v[1]/1000]),0x8f9a80);
      const xs=p.contour.map(v=>v[0]/1000),ys=p.contour.map(v=>v[1]/1000);
      this.objects.set(p.piece_id,{mesh,edge,window:win.id,baseColor:mat.color.clone(),center:[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2]});
    }
    for(const path of plan.paths){
      const points=path.points.map(v=>[v[0]/1000-this.w/2,.872,v[1]/1000-this.l/2]);
      const obj=this.line(this.dynamic,points,path.kind==='mark'?0x587bba:path.kind==='travel'?0x93aaa2:0xe56f27);
      obj.visible=false;this.paths.set(path.id,obj);
    }
    this.partial=this.line(this.dynamic,[[0,0,0],[0,0,0]],0xf2712d);
    if(plan.sewing_seams?.length&&this.equipment.has('pfaff'))this.sewing=new SewingViewer(this,this.equipment.get('pfaff'),plan);
  }
  apply(s){
    this.state=s;if(!this.plan)return;
    const win=this.plan.windows[s.window];
    const feed=s.operation==='load'?0:s.operation==='feed'?s.operation_progress:1;
    this.cloth.visible=feed>0&&feed<1;this.cloth.scale.set(win.width_mm/1000,1,win.length_mm/1000*Math.max(.001,feed));
    for(const [id,scrap] of this.scraps)scrap.visible=id===s.window&&feed>=1;
    this.cloth.position.set((win.width_mm/1000-this.w)/2,.862,win.length_mm/1000*feed/2-this.l/2);
    this.cloth.material.color.setHex(win.material==='rib'?0x8ba393:0xd7c9a5);
    this.roll.rotation.x=s.operation==='feed'?-feed*win.length_mm/160:0;
    this.targetHead=s.machine_id==='pfaff'?[-this.w/2,-this.l/2]:[s.head_mm[0]/1000-this.w/2,s.head_mm[1]/1000-this.l/2];
    if(s.status!=='playing'||this.lastRevision!==s.revision){this.head.position.x=this.targetHead[0];this.gantry.position.z=this.targetHead[1];}
    this.lastRevision=s.revision;
    this.head.position.y=s.tool==='up'||s.machine_id==='pfaff'?.025:0;this.blade.rotation.x=s.tool==='cut'?s.sim_time_s*10:0;
    this.light.material.color.setHex(s.vacuum?0x50d39b:0xdab45c);
    let count=0;
    for(const [id,o] of this.objects){
      const state=s.pieces[id],collected=['collected','sewing','sewn'].includes(state);
      const picking=s.operation==='pickup'&&s.piece_id===id?s.operation_progress:collected?1:0;
      o.mesh.visible=collected||(o.window===s.window&&feed>=1);
      if(s.machine_id==='pfaff')o.mesh.visible=s.operation==='transfer_to_sewing';
      const targetX=this.w/2+.75-o.center[0],targetZ=.45-o.center[1];
      o.mesh.position.set(-this.w/2+(targetX+this.w/2)*picking,.866*(1-picking)+(.705+.004*count)*picking+Math.sin(picking*Math.PI)*.3,-this.l/2+(targetZ+this.l/2)*picking);
      if(s.operation==='transfer_to_sewing'){
        const station=this.equipment.get('pfaff').position,f=s.operation_progress;
        o.mesh.position.lerp(new THREE.Vector3(station.x-o.center[0],.87+.004*count,station.z-o.center[1]),f);
        o.mesh.position.y+=Math.sin(f*Math.PI)*.35;
      }
      o.mesh.material.color.copy(o.baseColor);
      if(state==='cutting')o.mesh.material.color.setHex(0xe2b36a);
      if(state==='cut'||collected)o.mesh.material.color.setHex(collected?0x5da99a:0x9abc95);
      o.edge.visible=!collected; if(collected)count++;
    }
    const completed=new Set(s.completed_paths);
    for(const [id,obj] of this.paths){
      const p=this.plan.paths[id];obj.visible=p.window===s.window&&completed.has(id)&&p.kind!=='travel';
    }
    this.partial.visible=s.path_id!==null&&s.tool!=='up';
    if(this.partial.visible){
      const p=this.plan.paths[s.path_id];const d=p.distance_mm*s.path_progress;
      const pts=p.points.filter((_,i)=>p.cumulative_mm[i]<=d).concat([s.head_mm]);
      this.partial.geometry.dispose();this.partial.geometry=new THREE.BufferGeometry().setFromPoints(pts.map(v=>new THREE.Vector3(v[0]/1000-this.w/2,.88,v[1]/1000-this.l/2)));
    }
    this.sewing?.apply(s);
    if(s.machine_id==='pfaff'&&this.previousMachine!=='pfaff')this.focus('pfaff');
    this.previousMachine=s.machine_id;
  }
  cameraMode(mode){
    if(mode==='sewing'){this.focus('pfaff');return;}
    if(mode==='overview'){this.camera.position.set(5,7,4.5);this.controls.target.set(0,.6,-2.1);}
    else if(mode==='top'){this.camera.position.set(0,5,.001);this.controls.target.set(0,.7,0);}
    else {this.camera.position.set(3.7,3.6,4.4);this.controls.target.set(0,.7,0);}
    this.controls.update();
  }
  focus(id){const g=this.equipment.get(id);if(!g)return;const p=g.getWorldPosition(new THREE.Vector3());this.controls.target.copy(p).add(new THREE.Vector3(0,.85,0));this.camera.position.copy(p).add(id==='pfaff'?new THREE.Vector3(1.45,1.75,2):new THREE.Vector3(2.3,2.2,2.9));this.controls.update();}
  resize(){const r=this.canvas.parentElement.getBoundingClientRect();if(!r.width||!r.height)return;this.renderer.setSize(r.width,r.height,false);this.camera.aspect=r.width/r.height;this.camera.updateProjectionMatrix();}
  clear(){this.sewing?.dispose();this.sewing=null;this.previousMachine=null;this.plan=null;this.state=null;this.targetHead=null;this.disposeGroup(this.dynamic);this.objects.clear();this.paths.clear();this.makeCutter(1.6,2);}
}
