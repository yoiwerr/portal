/**
 * Portal — Ash & Ember Particle System
 * Three.js: smoke layers + slow ember drift. Berserk vibe.
 */
class AshField {
  constructor() {
    this.THREE = null;
    this.scene = null; this.camera = null; this.renderer = null;
    this.layers = []; this.mouse = { x: 0, y: 0, tx: 0, ty: 0 };
    this.scrollY = 0; this.time = 0; this.width = 0; this.height = 0;
    this.frameId = null; this.disposed = false;

    if (typeof window !== 'undefined' && window.THREE) {
      this.THREE = window.THREE;
      this._init();
    }
  }

  _init() {
    const T = this.THREE;
    const canvas = document.getElementById('bg-canvas');
    if (!canvas) return;

    this.renderer = new T.WebGLRenderer({ canvas, alpha: true, antialias: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);

    this.scene = new T.Scene();
    this.camera = new T.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.5, 60);
    this.camera.position.z = 14;
    this.width = window.innerWidth; this.height = window.innerHeight;

    // Texture: organic ash speck
    const tex = this._makeTexture();
    this._createLayers(tex);

    this._onResize = this._onResize.bind(this);
    this._onMouse = this._onMouse.bind(this);
    this._onScroll = this._onScroll.bind(this);
    window.addEventListener('resize', this._onResize);
    window.addEventListener('mousemove', this._onMouse);
    window.addEventListener('scroll', this._onScroll, { passive: true });

    this._loop();
  }

  _makeTexture() {
    const T = this.THREE;
    const s = 128;
    const c = document.createElement('canvas');
    c.width = c.height = s;
    const ctx = c.getContext('2d');

    // Radial gradient: dense center, feathery edge
    const g = ctx.createRadialGradient(s/2, s/2, 0, s/2, s/2, s/2);
    g.addColorStop(0,    'rgba(180,160,140,0.55)');
    g.addColorStop(0.06, 'rgba(160,140,120,0.40)');
    g.addColorStop(0.18, 'rgba(120,100,85,0.20)');
    g.addColorStop(0.40, 'rgba(70,55,45,0.07)');
    g.addColorStop(0.70, 'rgba(30,20,15,0.015)');
    g.addColorStop(1,    'rgba(0,0,0,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, s, s);

    // Noise
    const id = ctx.getImageData(0, 0, s, s);
    for (let i = 0; i < id.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 14;
      id.data[i + 3] = Math.max(0, Math.min(255, id.data[i + 3] + n));
    }
    ctx.putImageData(id, 0, 0);

    const tex = new T.CanvasTexture(c);
    tex.needsUpdate = true;
    return tex;
  }

  _createLayers(tex) {
    const T = this.THREE;
    const defs = [
      // Deep smoke — heavy, slow, far
      { n:150, spread:26, size:3.0, speed:0.04, rgb:[0.18,0.16,0.14], op:0.18, z0:-7, zR:5 },
      // Mid ash
      { n:250, spread:22, size:1.6, speed:0.09, rgb:[0.28,0.25,0.22], op:0.28, z0:-4, zR:7 },
      // Fine dust
      { n:300, spread:18, size:0.7, speed:0.15, rgb:[0.38,0.34,0.30], op:0.35, z0:-2, zR:9 },
      // Embers — faint red tint
      { n:160, spread:15, size:0.45, speed:0.20, rgb:[0.45,0.32,0.26], op:0.42, z0:0, zR:7 },
      // Sparks
      { n:100, spread:12, size:0.22, speed:0.30, rgb:[0.52,0.38,0.30], op:0.48, z0:1, zR:5 },
    ];

    for (const d of defs) {
      const pos = new Float32Array(d.n * 3);
      const sizes = new Float32Array(d.n);
      for (let i = 0; i < d.n; i++) {
        pos[i*3]   = (Math.random()-0.5)*d.spread*2;
        pos[i*3+1] = (Math.random()-0.5)*d.spread*2*(this.height/this.width);
        pos[i*3+2] = d.z0 + (Math.random()-0.5)*d.zR;
        sizes[i]   = d.size*(0.4+Math.random()*1.2);
      }
      const geo = new T.BufferGeometry();
      geo.setAttribute('position', new T.BufferAttribute(pos, 3));
      geo.setAttribute('size', new T.BufferAttribute(sizes, 1));

      const mat = new T.PointsMaterial({
        map: tex, color: new T.Color(d.rgb[0], d.rgb[1], d.rgb[2]),
        size: d.size, blending: T.AdditiveBlending,
        depthWrite: false, depthTest: true, transparent: true, opacity: d.op,
      });

      const points = new T.Points(geo, mat);
      this.scene.add(points);
      this.layers.push({ points, def: d, orig: new Float32Array(pos) });
    }
  }

  _onResize() { if (this.disposed) return;
    this.width=window.innerWidth; this.height=window.innerHeight;
    this.renderer.setSize(this.width,this.height);
    this.camera.aspect=this.width/this.height; this.camera.updateProjectionMatrix();
  }
  _onMouse(e) { if (this.disposed) return;
    this.mouse.tx=(e.clientX/this.width)*2-1;
    this.mouse.ty=-(e.clientY/this.height)*2+1;
  }
  _onScroll() { if (this.disposed) return; this.scrollY=window.scrollY; }

  _loop() { if (this.disposed) return;
    this.frameId=requestAnimationFrame(()=>this._loop());
    const t=this.time+=0.008;
    this.mouse.x+=(this.mouse.tx-this.mouse.x)*0.025;
    this.mouse.y+=(this.mouse.ty-this.mouse.y)*0.025;
    const sf=this.scrollY*0.0002;

    for (const L of this.layers) {
      const pa=L.points.geometry.attributes.position.array;
      const p=1+L.def.z0*0.05;
      for (let i=0;i<L.def.n;i++) {
        const i3=i*3; const ox=L.orig[i3]; const oy=L.orig[i3+1];
        const ph=ox*0.6+oy*0.4;
        pa[i3]  =ox+Math.sin(t*L.def.speed*0.6+ph)*1.1+this.mouse.x*L.def.spread*0.22*p;
        pa[i3+1]=oy+Math.cos(t*L.def.speed*0.5+ph*1.4)*0.9+this.mouse.y*L.def.spread*0.18*p-sf*L.def.speed*6*p;
      }
      L.points.geometry.attributes.position.needsUpdate=true;
      L.points.material.opacity=L.def.op*(0.82+0.18*Math.sin(t*0.3+L.def.z0));
    }
    this.camera.position.x+=(this.mouse.x*0.25-this.camera.position.x)*0.018;
    this.camera.position.y+=(this.mouse.y*0.18-this.camera.position.y)*0.018;
    this.camera.lookAt(0,0,0);
    this.renderer.render(this.scene,this.camera);
  }

  dispose() {
    this.disposed=true; if(this.frameId)cancelAnimationFrame(this.frameId);
    window.removeEventListener('resize',this._onResize);
    window.removeEventListener('mousemove',this._onMouse);
    window.removeEventListener('scroll',this._onScroll);
    if(this.scene){for(const L of this.layers){L.points.geometry.dispose();L.points.material.dispose();this.scene.remove(L.points);}this.layers=[];}
    if(this.renderer){this.renderer.dispose();}
    this.scene=this.camera=this.renderer=null;
  }
}

// Auto-start
if (document.readyState==='loading') {
  document.addEventListener('DOMContentLoaded',()=>{ window._ash=new AshField(); });
} else { window._ash=new AshField(); }
