// three.js viewer: the scan, then the measurement curves and landmarks on
// it. Canonical frame is Y-up in millimetres; the scene is metres.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const SCALE = 0.001;

export class Viewer {
  constructor(canvas, labelsEl) {
    this.canvas = canvas;
    this.labelsEl = labelsEl;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.01, 50);
    this.camera.position.set(0, 1.0, 3.2);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0.9, 0);

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(2, 3, 2.5);
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(-2.5, 1.5, -2);
    this.scene.add(fill);

    this.meshGroup = new THREE.Group();
    this.curveGroup = new THREE.Group();
    this.landmarkGroup = new THREE.Group();
    this.scene.add(this.meshGroup, this.curveGroup, this.landmarkGroup);
    this.labels = [];       // {position: Vector3, text, cls, el, objects: [Object3D]}
    this.showLabels = true;
    this.focus = null;      // the label being held down, if any — everything else hides
    this._restore = () => this.setFocus(null);
    // Labels never take the pointer: the canvas gets every press, so
    // OrbitControls orbits exactly as it always did. The canvas just asks,
    // on the way in, whether the press landed on a label — and if so, that
    // measurement is shown alone until the button is released.
    canvas.addEventListener("pointerdown", (e) => {
      const label = this._hit(e.clientX, e.clientY);
      if (!label) return;
      this.setFocus(label);
      window.addEventListener("pointerup", this._restore, { once: true });
      window.addEventListener("pointercancel", this._restore, { once: true });
    });
    // A double-click on a label asks the page to open a report on it.
    this.onReport = null;
    canvas.addEventListener("dblclick", (e) => {
      const label = this._hit(e.clientX, e.clientY);
      if (!label || !this.onReport) return;
      e.preventDefault();
      const box = canvas.parentElement.getBoundingClientRect();
      this.onReport(label, { x: e.clientX - box.left, y: e.clientY - box.top });
    });
    // A click on the body (a press that did not turn into a drag, and did
    // not land on a label) shows the point's canonical coordinates in mm.
    this.raycaster = new THREE.Raycaster();
    this.probe = new THREE.Mesh(new THREE.SphereGeometry(0.006, 10, 10),
                                new THREE.MeshBasicMaterial({ color: 0xd86018 }));
    this.probe.visible = false;
    this.probe.renderOrder = 4;
    this.scene.add(this.probe);
    this._press = null;
    canvas.addEventListener("pointerdown", (e) => { this._press = { x: e.clientX, y: e.clientY }; });
    canvas.addEventListener("pointerup", (e) => {
      const press = this._press;
      this._press = null;
      if (!press || Math.hypot(e.clientX - press.x, e.clientY - press.y) > 4) return;
      if (this._hit(e.clientX, e.clientY)) return;
      this._probeAt(e.clientX, e.clientY);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (e.buttons) return;
      const label = this._hit(e.clientX, e.clientY);
      canvas.style.cursor = label ? "pointer" : "";
      for (const other of this.labels) if (other.el) other.el.classList.toggle("hot", other === label);
    });

    this.resize = this.resize.bind(this);
    new ResizeObserver(this.resize).observe(canvas.parentElement);
    this.resize();
    this._loop();
  }

  resize() {
    const box = this.canvas.parentElement.getBoundingClientRect();
    const w = Math.max(1, Math.floor(box.width)), h = Math.max(1, Math.floor(box.height));
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  _loop() {
    requestAnimationFrame(() => this._loop());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this._placeLabels();
  }

  _clear(group) {
    while (group.children.length) {
      const child = group.children.pop();
      if (child.geometry) child.geometry.dispose();
      if (child.material) child.material.dispose();
    }
  }

  setMeshFromBuffer(buffer) {
    const view = new DataView(buffer);
    const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
    if (magic !== "STUM") throw new Error("not a studio mesh buffer");
    const nV = view.getUint32(4, true), nF = view.getUint32(8, true), flags = view.getUint32(12, true);
    const vertices = new Float32Array(buffer, 16, nV * 3);
    const faces = new Uint32Array(buffer, 16 + nV * 12, nF * 3);
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(vertices.length);
    for (let i = 0; i < vertices.length; i++) positions[i] = vertices[i] * SCALE;
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setIndex(new THREE.BufferAttribute(faces, 1));
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();

    this._clear(this.meshGroup);
    this.clearCurves();
    const material = new THREE.MeshStandardMaterial({
      color: 0xc7d2da, roughness: 0.75, metalness: 0.0, side: THREE.DoubleSide, flatShading: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    this.meshGroup.add(mesh);
    this._fit(geometry.boundingBox);
    return { nV, nF, decimated: (flags & 1) === 1 };
  }

  _fit(box) {
    const size = new THREE.Vector3(); box.getSize(size);
    const centre = new THREE.Vector3(); box.getCenter(centre);
    const radius = Math.max(size.x, size.y, size.z) * 0.55;
    const dist = radius / Math.tan((this.camera.fov * Math.PI) / 360) * 1.05;
    this.controls.target.copy(centre);
    this.camera.position.set(centre.x + dist * 0.35, centre.y + radius * 0.15, centre.z + dist);
    this.camera.near = dist / 100;
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  clearCurves() {
    this._clear(this.curveGroup);
    this._clear(this.landmarkGroup);
    this.focus = null;
    this.labels = [];
    this.labelsEl.innerHTML = "";
  }

  setCurves(curves) {
    this._clear(this.curveGroup);
    this.labels = this.labels.filter((l) => l.cls === "lm");
    let owner = null;       // an unlabelled curve (the other arm's ring) belongs to the last label
    for (const curve of curves) {
      const pts = curve.points.map((p) => new THREE.Vector3(p[0] * SCALE, p[1] * SCALE, p[2] * SCALE));
      if (pts.length < 2) continue;
      const geometry = new THREE.BufferGeometry().setFromPoints(pts);
      const colour = new THREE.Color(curve.colour || "#1E5F8C");
      const material = new THREE.LineBasicMaterial({ color: colour, linewidth: 2 });
      const line = curve.kind === "loop" ? new THREE.LineLoop(geometry, material) : new THREE.Line(geometry, material);
      line.renderOrder = 2;
      this.curveGroup.add(line);
      // a slightly thicker halo, because WebGL ignores linewidth
      const halo = new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity: 0.35 });
      const shadow = curve.kind === "loop" ? new THREE.LineLoop(geometry, halo) : new THREE.Line(geometry, halo);
      shadow.scale.setScalar(1.004);
      this.curveGroup.add(shadow);
      if (curve.label) {
        const anchor = curve.kind === "loop" ? this._extreme(pts, +1) : pts[Math.floor(pts.length / 2)];
        const proto = curve.colour === "#B85042";
        const m = /(-?[\d.]+)\s*(mm|deg)\s*$/.exec(curve.label);
        owner = this._label(anchor, curve.label, proto ? "proto" : "spec", [line, shadow], {
          target: proto ? "prototype" : "measurement", key: curve.key || null,
          value: m ? Number(m[1]) : null, unit: m ? m[2] : "mm",
        });
      } else if (owner) {
        owner.objects.push(line, shadow);
      }
    }
    this._renderLabelEls();
  }

  setLandmarks(points) {
    this._clear(this.landmarkGroup);
    this.labels = this.labels.filter((l) => l.cls !== "lm");
    const material = new THREE.MeshStandardMaterial({ color: 0x20303f, roughness: 0.5 });
    const geometry = new THREE.SphereGeometry(0.008, 12, 12);
    for (const [name, lm] of Object.entries(points || {})) {
      const p = lm.position_mm;
      if (!p) continue;
      const sphere = new THREE.Mesh(geometry, material);
      sphere.position.set(p[0] * SCALE, p[1] * SCALE, p[2] * SCALE);
      sphere.renderOrder = 3;
      this.landmarkGroup.add(sphere);
      this._label(sphere.position.clone(), name.replace(/_/g, " "), "lm", [sphere],
                  { target: "landmark", key: name, value: p.map((v) => Math.round(v * 10) / 10), unit: "mm" });
    }
    this._renderLabelEls();
  }

  _extreme(pts, sign) {
    let best = pts[0];
    for (const p of pts) if (sign * p.x > sign * best.x) best = p;
    return best;
  }

  _label(position, text, cls, objects = [], meta = {}) {
    const label = { position, text, cls, el: null, objects, meta };
    this.labels.push(label);
    return label;
  }

  _renderLabelEls() {
    this.labelsEl.innerHTML = "";
    for (const label of this.labels) {
      const el = document.createElement("span");
      el.textContent = label.text;
      el.className = label.cls;
      this.labelsEl.appendChild(el);
      label.el = el;
    }
  }

  /** Cast into the body at a viewport point; show its coordinates, or hide. */
  _probeAt(clientX, clientY) {
    const box = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((clientX - box.left) / box.width) * 2 - 1,
                                  -((clientY - box.top) / box.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const hits = this.meshGroup.visible ? this.raycaster.intersectObjects(this.meshGroup.children, false) : [];
    if (!hits.length) { this.hideProbe(); return; }
    const p = hits[0].point;
    this.probe.position.copy(p);
    this.probe.visible = true;
    const mm = [p.x / SCALE, p.y / SCALE, p.z / SCALE];
    if (this.onProbe) this.onProbe({ mm, x: clientX - box.left, y: clientY - box.top });
  }

  hideProbe() {
    this.probe.visible = false;
    if (this.onProbe) this.onProbe(null);
  }

  /** The visible label under a viewport point, if any. */
  _hit(clientX, clientY) {
    for (const label of this.labels) {
      const el = label.el;
      if (!el || el.style.display === "none") continue;
      const r = el.getBoundingClientRect();
      if (clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom) return label;
    }
    return null;
  }

  /** Show only `label`'s geometry and text (null = everything). */
  setFocus(label) {
    this.focus = label;
    for (const other of this.labels) {
      const on = !label || other === label;
      for (const object of other.objects) object.visible = on;
    }
  }

  _placeLabels() {
    if (!this.labels.length) return;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    const v = new THREE.Vector3();
    for (const label of this.labels) {
      if (!label.el) continue;
      const visible = this.showLabels && (!this.focus || label === this.focus) &&
        ((label.cls === "lm" && this.landmarkGroup.visible) || (label.cls !== "lm" && this.curveGroup.visible));
      if (!visible) { label.el.style.display = "none"; continue; }
      v.copy(label.position).project(this.camera);
      if (v.z > 1) { label.el.style.display = "none"; continue; }
      label.el.style.display = "";
      label.el.style.left = `${(v.x * 0.5 + 0.5) * w}px`;
      label.el.style.top = `${(-v.y * 0.5 + 0.5) * h}px`;
    }
  }

  toggle(what, on) {
    if (what === "mesh") this.meshGroup.visible = on;
    if (what === "curves") this.curveGroup.visible = on;
    if (what === "landmarks") this.landmarkGroup.visible = on;
    if (what === "labels") this.showLabels = on;
  }
}
