/* 大肥鱼的小屋：Three.js 等距房间 + 世界状态映射 */
(function(){
  let inited=false, scene, camera, renderer, controls, raycaster, mouse, clock;
  let room, charGroup, customModel=null, rain=null, hotspots=[], hud, infoBox;
  let lastState=null, lastActivity='', t0=0, statusEl;

  function init(){
    if(inited) return; inited=true;
    const canvas=document.getElementById('homecanvas');
    if(!canvas || !window.THREE) return;
    const wrap=canvas.parentElement;
    renderer=new THREE.WebGLRenderer({canvas, antialias:true, alpha:false});
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio||1));
    renderer.shadowMap.enabled=true;
    scene=new THREE.Scene();
    scene.background=new THREE.Color(0x0b1020);
    camera=new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(9.5, 10.5, 9.5);
    controls=new THREE.OrbitControls(camera, canvas);
    controls.target.set(0,1.2,0);
    controls.enablePan=false;
    controls.minDistance=9; controls.maxDistance=22;
    controls.maxPolarAngle=Math.PI/2.15;
    controls.enableDamping=true;
    raycaster=new THREE.Raycaster(); mouse=new THREE.Vector2(); clock=new THREE.Clock();
    hud=document.getElementById('homehud'); infoBox=document.getElementById('homeinfo');
    statusEl=document.getElementById('homehud');
    scene.add(new THREE.HemisphereLight(0xbfd4ff, 0x1a2030, 0.9));
    const key=new THREE.DirectionalLight(0xffe2b8, 1.1);
    key.position.set(5,10,4); key.castShadow=true; key.shadow.mapSize.set(1024,1024);
    scene.add(key);
    const lamp=new THREE.PointLight(0xffc98a, 0.8, 12); lamp.position.set(-2.5,2.8,-2.5); scene.add(lamp);
    buildRoom(); buildCharacter(); buildHotspots();
    canvas.addEventListener('pointerdown', onPick);
    window.addEventListener('resize', resize); resize();
    refresh(); animate();
    setInterval(refresh, 5000);
  }

  function resize(){
    const c=document.getElementById('homecanvas'); if(!c) return;
    const w=c.clientWidth||800, h=c.clientHeight||480;
    renderer.setSize(w,h,false); camera.aspect=w/h; camera.updateProjectionMatrix();
  }

  function box(w,h,d,color,x,y,z,parent,opts){
    const g=new THREE.Mesh(new THREE.BoxGeometry(w,h,d), new THREE.MeshStandardMaterial({color, roughness:(opts&&opts.roughness)||0.85, metalness:0.02}));
    g.position.set(x,y,z); g.castShadow=true; g.receiveShadow=true; (parent||scene).add(g); return g;
  }
  function cyl(r,h,color,x,y,z,parent){
    const g=new THREE.Mesh(new THREE.CylinderGeometry(r,r,h,20), new THREE.MeshStandardMaterial({color, roughness:0.8}));
    g.position.set(x,y,z); g.castShadow=true; (parent||scene).add(g); return g;
  }

  function buildRoom(){
    room=new THREE.Group(); scene.add(room);
    // 地板与墙
    box(9,0.25,9,0x8a6a4f,0,-0.12,0,room);
    const wallMat=new THREE.MeshStandardMaterial({color:0xbfd9e8, roughness:0.95, side:THREE.DoubleSide});
    const back=new THREE.Mesh(new THREE.PlaneGeometry(9,4.4),wallMat); back.position.set(0,2.2,-4.5); back.receiveShadow=true; room.add(back);
    const left=new THREE.Mesh(new THREE.PlaneGeometry(9,4.4),wallMat); left.rotation.y=Math.PI/2; left.position.set(-4.5,2.2,0); left.receiveShadow=true; room.add(left);
    // 窗
    box(2.6,1.7,0.1,0x2b4a6f,1.5,2.6,-4.42,room);
    box(2.9,0.12,0.18,0xf2ead8,1.5,3.5,-4.38,room);
    box(2.9,0.12,0.18,0xf2ead8,1.5,1.7,-4.38,room);
    // 床
    box(3.2,0.35,1.9,0x6d4c41,-2.4,0.25,-2.9,room);
    box(3.0,0.28,1.7,0xdfe9f5,-2.4,0.5,-2.9,room);
    box(3.0,0.18,0.6,0x9fc6e8,-2.4,0.7,-3.4,room);
    box(0.18,0.9,1.9,0x5d4037,-3.95,0.65,-2.9,room);
    // 桌子
    box(2.4,0.16,1.2,0xc9a77c,1.4,0.75,-2.9,room);
    [[0.4,0.4],[2.4,0.4],[0.4,-0.4],[2.4,-0.4]].forEach(p=>box(0.12,0.75,0.12,0x8d6e63,1.4+p[0]/2,0.38,-2.9+p[1],room));
    // 椅子
    box(0.8,0.1,0.8,0x8d6e63,1.4,0.5,-1.9,room);
    box(0.1,0.9,0.8,0x8d6e63,1.0,0.9,-1.9,room);
    // 灶台/冰箱
    box(2.2,1.2,1.2,0xe8eef5,2.9,0.6,-4.0,room);
    box(0.9,0.35,0.7,0x3a3f4a,2.6,1.28,-3.95,room);
    cyl(0.18,0.35,0xbfc7d1,3.3,1.25,-3.95,room);
    box(1.1,2.3,1.1,0xd8e3ee,3.8,1.15,-2.4,room);
    // 沙发
    box(2.8,0.45,1.1,0x5b7fa8,-2.4,0.35,1.9,room);
    box(2.8,0.7,0.25,0x4d6f96,-2.4,0.75,2.35,room);
    box(0.25,0.6,1.1,0x4d6f96,-3.8,0.55,1.9,room);
    box(0.25,0.6,1.1,0x4d6f96,-1.0,0.55,1.9,room);
    // 小地毯
    box(3.2,0.03,2.2,0x7d5a7a,0,0.02,0.2,room);
    // 灯
    cyl(0.05,2.2,0x555b66,-2.4,1.1,1.9,room);
    cyl(0.45,0.3,0xffd79a,-2.4,2.25,1.9,room);
    // 窗外的夜色
    box(3.0,1.9,0.05,0x0d1b3a,1.5,2.6,-4.55,room);
  }

  function buildCharacter(){
    charGroup=new THREE.Group(); charGroup.position.set(0,0,0.2); scene.add(charGroup);
    const skin=0xffe0cc, hair=0x2f5fa8, dress=0xffffff, apron=0xeef4fb;
    const body=cyl(0.34,0.8,dress,0,0.85,0,charGroup); body.scale.z=0.8;
    const skirt=new THREE.Mesh(new THREE.ConeGeometry(0.55,0.7,20), new THREE.MeshStandardMaterial({color:0x3f6fb5,roughness:0.9}));
    skirt.position.set(0,0.55,0); skirt.castShadow=true; charGroup.add(skirt);
    const head=new THREE.Mesh(new THREE.SphereGeometry(0.42,24,20), new THREE.MeshStandardMaterial({color:skin,roughness:0.9}));
    head.position.set(0,1.68,0); head.castShadow=true; charGroup.add(head);
    // 头发
    const hairCap=new THREE.Mesh(new THREE.SphereGeometry(0.47,24,18,0,Math.PI*2,0,Math.PI*0.62), new THREE.MeshStandardMaterial({color:hair,roughness:0.9}));
    hairCap.position.set(0,1.74,0); charGroup.add(hairCap);
    for(let i=-2;i<=2;i++){
      const strand=new THREE.Mesh(new THREE.CylinderGeometry(0.1,0.1,0.55,8), new THREE.MeshStandardMaterial({color:hair}));
      strand.position.set(i*0.13,1.35,-0.3); strand.rotation.x=0.12; charGroup.add(strand);
    }
    // 眼睛
    [-0.16,0.16].forEach(x=>{
      const eye=new THREE.Mesh(new THREE.SphereGeometry(0.055,12,10), new THREE.MeshBasicMaterial({color:0x1b2a4a}));
      eye.position.set(x,1.7,0.37); charGroup.add(eye);
    });
    // 手臂
    const armL=new THREE.Mesh(new THREE.CylinderGeometry(0.08,0.08,0.5,8), new THREE.MeshStandardMaterial({color:skin}));
    armL.position.set(-0.4,1.05,0); armL.rotation.z=0.25; charGroup.add(armL);
    const armR=armL.clone(); armR.position.x=0.4; armR.rotation.z=-0.25; charGroup.add(armR);
    charGroup.userData.arms=[armL,armR];
    // 围裙
    const ap=new THREE.Mesh(new THREE.PlaneGeometry(0.5,0.7), new THREE.MeshStandardMaterial({color:apron,side:THREE.DoubleSide}));
    ap.position.set(0,0.85,0.3); charGroup.add(ap);
    charGroup.scale.set(1.2,1.2,1.2);
  }

  function buildHotspots(){
    const pts=[
      {x:-2.4,y:1.2,z:-2.9,info:'床：被子摊开着，枕头上还有压痕'},
      {x:2.9,y:1.7,z:-3.9,info:'灶台：锅里还温着，旁边放着没洗的碗'},
      {x:1.5,y:2.6,z:-4.2,info:'窗：外面是城市的夜，偶尔有车灯划过'},
      {x:1.4,y:1.1,z:-2.9,info:'书桌：电脑还亮着，旁边是没喝完的水'},
      {x:-2.4,y:1.0,z:1.9,info:'沙发：毯子皱成一团，遥控器掉在缝里'}
    ];
    pts.forEach(p=>{
      const m=new THREE.Mesh(new THREE.SphereGeometry(0.11,16,12), new THREE.MeshBasicMaterial({color:0x7dd3fc}));
      m.position.set(p.x,p.y,p.z); m.userData.info=p.info; scene.add(m); hotspots.push(m);
    });
  }

  function setActivity(activity){
    if(!charGroup) return;
    activity=String(activity||'');
    lastActivity=activity;
    const arms=charGroup.userData.arms||[];
    charGroup.rotation.set(0,0,0); charGroup.position.set(0,0,0.2);
    arms.forEach(a=>a.rotation.x=0);
    if(activity.includes('睡')){
      charGroup.position.set(-2.4,0.62,-2.9); charGroup.rotation.z=Math.PI/2; charGroup.rotation.y=0.1;
    }else if(activity.includes('做饭')||activity.includes('炒')||activity.includes('煮')){
      charGroup.position.set(2.3,0,-3.3); charGroup.rotation.y=-0.5;
    }else if(activity.includes('吃')){
      charGroup.position.set(1.4,0,-1.8); charGroup.rotation.y=Math.PI;
    }else if(activity.includes('上班')||activity.includes('工作')||activity.includes('电脑')){
      charGroup.position.set(1.4,0,-2.1); charGroup.rotation.y=Math.PI;
    }else if(activity.includes('沙发')||activity.includes('刷手机')||activity.includes('看剧')||activity.includes('听歌')||activity.includes('游戏')||activity.includes('发呆')||activity.includes('看书')){
      charGroup.position.set(-2.2,0,1.9); charGroup.rotation.y=0.2;
    }else if(activity.includes('洗澡')){
      charGroup.position.set(3.4,0,0.8); charGroup.rotation.y=-1.2;
    }
  }

  async function refresh(){
    try{
      const r=await fetch(B+'/api/world/state').then(x=>x.json());
      if(r.code!==0) return;
      const st=r.state||{}; lastState=st;
      const clockTxt=st.clock||'';
      const m=clockTxt.match(/(\d{1,2}):(\d{2})/); const hour=m?parseInt(m[1]):14;
      const isNight=hour<7||hour>=19;
      scene.background=new THREE.Color(isNight?0x0b1020:0x9fc6e8);
      if(hud){
        hud.innerHTML='<b>大肥鱼</b> · '+(st.place||'家')+' · '+(st.activity||'待着')+
          '<br><span style="color:#9aa4b8">'+(st.clock||'')+' · 心情 '+(st.mood_text||st.mood||'平静')+
          ' · 精力 '+Math.round(st.energy||0)+'</span>';
      }
      setActivity(st.activity);
      toggleRain(String(st.weather||'').includes('雨') || String(st.weather||'').includes('rain'));
    }catch(e){ if(hud) hud.textContent='世界状态加载失败'; }
  }

  function toggleRain(on){
    if(on && !rain){
      const geo=new THREE.BufferGeometry(); const n=600; const pos=new Float32Array(n*3);
      for(let i=0;i<n;i++){ pos[i*3]=Math.random()*10-5; pos[i*3+1]=Math.random()*6; pos[i*3+2]=Math.random()*9-4.5; }
      geo.setAttribute('position',new THREE.BufferAttribute(pos,3));
      rain=new THREE.Points(geo,new THREE.PointsMaterial({color:0x9ec9ff,size:0.06,transparent:true,opacity:0.6}));
      scene.add(rain);
    }else if(!on && rain){ scene.remove(rain); rain=null; }
  }

  function onPick(ev){
    const c=document.getElementById('homecanvas'); if(!c) return;
    const rect=c.getBoundingClientRect();
    mouse.x=((ev.clientX-rect.left)/rect.width)*2-1;
    mouse.y=-((ev.clientY-rect.top)/rect.height)*2+1;
    raycaster.setFromCamera(mouse,camera);
    const hits=raycaster.intersectObjects(hotspots,false);
    if(hits.length && infoBox){
      infoBox.textContent=hits[0].object.userData.info||'';
      infoBox.style.display='block';
      clearTimeout(infoBox._t); infoBox._t=setTimeout(()=>{infoBox.style.display='none';},4000);
    }
  }

  function animate(){
    requestAnimationFrame(animate);
    const t=clock.getElapsedTime();
    if(controls) controls.update();
    if(rain){ const p=rain.geometry.attributes.position; for(let i=0;i<p.count;i++){ p.setY(i,p.getY(i)-0.06); if(p.getY(i)<0) p.setY(i,6); } p.needsUpdate=true; }
    if(charGroup){
      if(lastActivity.includes('睡')) charGroup.position.y=0.62+Math.sin(t*1.2)*0.01;
      else charGroup.position.y=0.02+Math.sin(t*1.6)*0.02;
      const arms=charGroup.userData.arms||[];
      if(lastActivity.includes('做饭')||lastActivity.includes('炒')){ arms.forEach((a,i)=>a.rotation.x=Math.sin(t*4+i)*0.5); }
      else if(lastActivity.includes('刷手机')||lastActivity.includes('工作')||lastActivity.includes('电脑')){ arms[0].rotation.x=-0.9; arms[1].rotation.x=-0.9; }
      else { arms.forEach(a=>a.rotation.x=Math.sin(t*1.4)*0.12); }
    }
    if(renderer && scene && camera) renderer.render(scene,camera);
  }

  window.initHome3D=init;

  window.loadCustomModel=function(){
    const url=(document.getElementById('homemodel')||{}).value||'';
    if(!url) return;
    if(!window.THREE || !THREE.GLTFLoader){ alert('模型加载器未加载'); return; }
    new THREE.GLTFLoader().load(url, function(gltf){
      if(customModel){ scene.remove(customModel); }
      customModel=gltf.scene; customModel.scale.set(1,1,1); customModel.position.set(0,0,0);
      scene.add(customModel);
      if(charGroup) charGroup.visible=false;
      document.getElementById('homehint').textContent='已加载自定义模型';
    }, undefined, function(e){ document.getElementById('homehint').textContent='模型加载失败：'+e; });
  };
  window.resetHomeView=function(){
    if(!camera) return;
    camera.position.set(9.5,10.5,9.5); controls.target.set(0,1.2,0); controls.update();
  };
})();
