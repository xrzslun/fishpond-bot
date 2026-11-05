
const B = window.__FP_BASE__ || '';
function el(id){return document.getElementById(id)}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function novicePill(name, ok, detail){
  const color = ok ? '#16a34a' : '#dc2626';
  return '<span style="display:inline-flex;align-items:center;gap:6px;background:#12151c;border:1px solid #2a2f3a;border-radius:999px;padding:6px 12px;font-size:13px">'+
    '<span style="width:8px;height:8px;border-radius:50%;background:'+color+'"></span>'+name+'：'+(ok?'正常':'不正常')+
    (detail?'<span style="color:#6b7280;font-size:12px">（'+detail+'）</span>':'')+'</span>';
}
async function noviceCheck(){
  const out = el('novice-out'), pills = el('novice-pills');
  out.textContent = '检查中…'; pills.innerHTML='';
  let lines = [], problems = false;
  try{
    const st = await fetch(B+'/api/status').then(r=>r.json());
    const online = !!st.bridge_connected;
    const qq = (st.qq && (st.qq.uin || st.qq.nickname)) ? (st.qq.uin||'已登录') : '';
    pills.innerHTML += novicePill('机器人', online, online?'正在替你聊天':'需要重启');
    if(!online) problems = true;
    lines.push(online ? '✅ 机器人程序在运行。' : '❌ 机器人程序没在运行，点「退出」旁边刷新页面试试，或联系 QQ：2844642318。');
    if(online && !qq) problems = true;
    if(online) lines.push(qq ? '✅ QQ 已登录：'+qq : '❌ QQ 还没登录，去「账号 → 扫码登录」用手机 QQ 扫一下。');
  }catch(e){ problems = true; pills.innerHTML += novicePill('机器人', false, '网页连不上'); lines.push('❌ 网页连不上服务器，先刷新页面。'); }
  try{
    const h = await fetch(B+'/api/health').then(r=>r.json());
    const issues = (h && h.issues) || [];
    if(issues.length) problems = true;
    pills.innerHTML += novicePill('服务器', issues.length===0, issues.length?issues[0]:'空间充足');
    lines.push(issues.length ? '⚠️ 服务器有一点小问题：'+issues.join('；')+'。不致命，可以先用。' : '✅ 服务器空间、内存都正常。');
  }catch(e){ problems = true; }
  try{
    const k = await fetch(B+'/api/apikey').then(r=>r.json());
    const ok = !!(k && k.configured);
    if(!ok) problems = true;
    pills.innerHTML += novicePill('AI 模型', ok, ok?'已配置':'还没填 Key');
    lines.push(ok ? '✅ AI 模型已配置，可以回复消息。' : '❌ AI 模型还没配置，去「机器人 → 模型」填上 Key（找 QQ：2844642318 要）。');
  }catch(e){ problems = true; }
  window.__noviceIssues = problems;
  el('novice-help').style.display = 'inline-block';
  el('novice-diag').style.display = problems ? 'inline-block' : 'none';
  out.textContent = lines.join('\n');
}
function noviceHelp(){
  alert('遇到问题按这个顺序试：\n\n1. 刷新网页（下拉刷新）\n2. 看「状态」页上面的红点，哪项不正常就点对应按钮\n3. QQ 掉线：账号 → 扫码登录，手机 QQ 扫一下\n4. 如果体检有红点：点「下载诊断包」，把文件发给 QQ：2844642318');
}
window.addEventListener('unhandledrejection', function(){
  try{ if(el('pbar')) el('pbar').textContent=''; }catch(e){}
});
function fmtUptime(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return (h?h+'小时':'')+m+'分钟'}

const GROUP_DEFS = [
  {key:'status', label:'状态', roles:['super','admin'], subs:{super:[['status','状态']],admin:[['status','状态']]}},
  {key:'bot', label:'机器人', roles:['super'], subs:{super:[['persona','人设'],['bili','B站'],['pv','模型'],['voice','语音'],['tokens','用量统计'],['selfcheck','接口自检'],['world','世界'],['rest','休息'],['slang','黑话'],['img','生图'],['mem','记忆'],['settings','设置']]}},
  {key:'chat', label:'聊天', roles:['super','admin'], subs:{
    super:[['auto','接话模式'],['gr','群聊回复'],['gm','群聊管理'],['rate','回复频率'],['kw','关键词'],['pf','回复前缀'],['end','结束语'],['stk','表情包'],['bored','无聊模式'],['game','剧本杀']],
    admin:[['auto','接话模式'],['gr','群聊回复'],['gm','群聊管理'],['rate','回复频率'],['kw','关键词'],['pf','回复前缀'],['end','结束语'],['stk','表情包'],['bored','无聊模式'],['game','剧本杀']]
  }},
  {key:'wl', label:'白名单', roles:['super','admin','user'], subs:{
    super:[['wl','白名单']],
    admin:[['wl','白名单']],
    user:[['wl','白名单']]
  }},
  {key:'superadmin', label:'超级管理员', roles:['super'], subs:{
    super:[['super','超级管理员']]
  }},
  {key:'host', label:'租户', roles:['super'], subs:{
    super:[['hosting','租户管理']]
  }},
  {key:'acct', label:'账号', roles:['super','admin'], subs:{
    super:[['qr','扫码登录'],['accounts','账号管理'],['logins','登录日志']],
    admin:[['accounts','账号管理'],['logins','登录日志']]
  }},
  {key:'logout', label:'退出'}
];
let CURRENT_ROLE = 'super';
const ALL_SECTIONS = '#status,#rest,#settings,#super,#bili,#gm,#persona,#pv,#voice,#qr,#wl,#kw,#pf,#auto,#gr,#end,#bored,#rate,#stk,#accounts,#logins,#mem,#slang,#img,#game,#hosting,#tokens,#selfcheck';
function showTab(name){
  document.querySelectorAll(ALL_SECTIONS).forEach(x=>x.classList.add('hidden'));
  const node = el(name);
  if(node) node.classList.remove('hidden');
  if(name==='wl') loadWL();
  if(name==='kw') loadKW();
  if(name==='pf') loadPrefix();
  if(name==='auto') loadAuto();
  if(name==='gr'){ loadGR(); loadMusic(); }
  if(name==='bili'){ loadBili(); biliAcctLoad(); }
  if(name==='gm'){ loadGMGroups(); loadGM(); }
  if(name==='bored') loadBored();
  if(name==='rest') loadRest();
  if(name==='settings') loadSettings();
  if(name==='super'){ loadSuper(); loadEconomy(); }
  if(name==='persona') loadPersona();
  if(name==='pv') loadProviders();
  if(name==='voice') loadVoice();
  if(name==='end') loadEnd();
  if(name==='rate') loadRate();
  if(name==='stk'){ loadStickers(); loadStickerPackInfo(); }
  if(name==='status') loadFriendBrief();
  if(name==='slang') loadSlang();
  if(name==='world') loadWorld();
  if(name==='img') loadImageCfg();
  if(name==='mem') loadMemory();
  if(name==='tokens') loadTokens();
  if(name==='selfcheck') loadTestMode();
  if(name==='game') loadGame();
  if(name==='hosting') loadHosting();
  if(name==='accounts') loadAccounts();
  if(name==='logins') loadLoginLogs();
}
async function loadWorld(){
  try{
    const r=await fetch(B+'/api/world/state').then(x=>x.json());
    if(r.code!==0){ el('world_state').textContent=r.message||'加载失败'; return; }
    const st=r.state||{}, on=String(st.enabled)==='1';
    const t=el('world_toggle'); t.textContent=on?'世界运行中（点击关闭）':'世界已关闭（点击开启）';
    t.style.background=on?'#16a34a':'#7f1d1d';
    const cardEl=el('world_card'); if(cardEl) cardEl.textContent=st.card||'';
    el('world_proactive_btn').textContent='主动消息：'+(String(st.proactive)==='1'?'开':'关');
    el('world_greet_btn').textContent='作息问候：'+(String(st.greetings)==='1'?'开':'关');
    if(el('world_share_max')&&!el('world_share_max').value) el('world_share_max').value=st.share_max||3;
    el('world_photo_btn').textContent='实况照片：'+(String(st.photo_enabled)==='1'?'开':'关');
    if(el('world_photo_max')&&!el('world_photo_max').value) el('world_photo_max').value=st.photo_max||3;
    fetch(B+'/api/world/tasks').then(x=>x.json()).then(function(r){
      el('world_tasks').innerHTML=(r.items||[]).map(function(t){
        const tag={doing:'进行中',done:'已完成',failed:'失败',cancelled:'已取消'}[t.status]||t.status;
        return '<div style="padding:6px 0;border-bottom:1px solid #1a1f28">'+t.title+' · '+tag+
          (t.done_text?' · '+t.done_text:'')+'</div>';
      }).join('')||'还没有任务';
    }).catch(function(){});
    el('world_money').textContent='现金：'+(st.money||0)+' 元'+
      ((st.goals||[]).length?('　目标：'+st.goals[0].title+' '+st.goals[0].progress+'/'+st.goals[0].target):'');
    el('world_ledger').innerHTML=(st.ledger||[]).map(function(x){
      return '<div>'+x.day_index+'天 '+x.amount+' 元 · '+x.reason+'</div>';
    }).join('')||'还没有账目';
    el('world_knowledge').innerHTML=(st.knowledge||[]).map(function(k){
      return '<div>'+k.name+'：'+k.text+'</div>';
    }).join('')||'还没有听说什么';
    el('world_state').textContent='世界时间：'+(st.clock||'')+'\n地点：'+(st.place||'')+'\n正在做：'+(st.activity||'')+
      '\n精力：'+(st.energy||0)+' / 100\n状态：'+(st.mood||'')+
      '\n饥饿：'+((st.needs||{}).hunger||0)+' / 100\n想聊天：'+((st.needs||{}).social||0)+' / 100'+
      '\n心情：'+(st.mood_text||'')+'（开心 '+((st.emotion||{}).joy||0)+' / 烦躁 '+((st.emotion||{}).anger||0)+
      ' / 低落 '+((st.emotion||{}).sad||0)+' / 压力 '+((st.emotion||{}).stress||0)+'）';
    fetch(B+'/api/weather').then(x=>x.json()).then(function(r){
      const w=r.weather||{};
      el('world_weather').textContent=w.city?((w.city+(w.district||''))+'　'+(w.text||'')+'　气温 '+(w.temp??'-')+'℃'):'还没有定位数据，点下面刷新';
    }).catch(function(){});
    fetch(B+'/api/world/summary').then(x=>x.json()).then(function(r){
      const items=(r.items||[]).map(function(it){
        return '<div style="padding:4px 0"><div style="display:flex;justify-content:space-between"><span>'+it.name+'</span><span style="color:#8b93a5">'+
          Math.floor(it.minutes/60)+' 小时 '+Math.round((it.minutes%60))+' 分</span></div>'+
          '<div style="height:6px;background:#1f242e;border-radius:4px;margin-top:3px"><div style="height:6px;width:'+it.pct+'%;background:#2563eb;border-radius:4px"></div></div></div>';
      }).join('');
      el('world_trend').innerHTML=(items||'还没有记录')+
        '<div style="margin-top:8px;color:#8b93a5;font-size:12px">今日事件 '+r.events+' 条 · 完成 '+(r.tasks_done||0)+' 件事 · 现金变化 '+
        (r.money_delta>0?'+':'')+r.money_delta+' 元</div>';
    }).catch(function(){});
    el('world_diary').textContent=(st.diary&&st.diary.text)||'还没有日记（跨天后自动生成）';
    el('world_npcs').innerHTML=(st.npcs||[]).map(function(n){
      return '<div style="padding:6px 0;border-bottom:1px solid #1a1f28">'+n.name+' · '+n.role+
        ' · 亲近度 '+n.closeness+'<div class="hint" style="margin-top:2px">'+n.traits+'</div></div>';
    }).join('')||'还没有认识的人';
    renderWorldEvents(r.events);
    fillWorldDays(r.days||[], r.today||0);
  }catch(e){ el('world_state').textContent='网络错误'; }
}
function worldDayLabel(day){
  const d=new Date(Date.UTC(2026,0,1)); d.setUTCDate(d.getUTCDate()+Number(day||0));
  return (d.getUTCMonth()+1)+'月'+d.getUTCDate()+'日';
}
function fillWorldDays(days, today){
  const sel=el('world_day'); if(!sel) return;
  const cur=sel.value;
  let html='';
  (days||[]).forEach(function(d){
    html+='<option value="'+d+'">'+(Number(d)===Number(today)?'今天 · ':'')+worldDayLabel(d)+'</option>';
  });
  sel.innerHTML=html||'<option value="'+today+'">今天</option>';
  sel.value=cur&&Array.from(sel.options).some(function(o){return o.value===cur;})?cur:String(today);
}
function renderWorldEvents(events){
  const KIND_TAG={wake:'被吵醒',wake_again:'又被吵醒',sleep:'睡着',meet:'偶遇',task:'任务',proactive:'主动分享',social:'心事',discover:'发现',move:'生活',photo:'照片'};
  const KIND_COLOR={wake:'#f59e0b',wake_again:'#f97316',sleep:'#6b7280',meet:'#38bdf8',task:'#22c55e',proactive:'#a855f7',social:'#ef4444',discover:'#eab308',move:'#64748b',photo:'#0ea5e9'};
  let html='';
  (events||[]).slice().reverse().forEach(function(e){
    const hh=String(Math.floor(e.minutes/60)).padStart(2,'0'), mm=String(e.minutes%60).padStart(2,'0');
    const tag=KIND_TAG[e.kind]||'生活', color=KIND_COLOR[e.kind]||'#64748b';
    let text=String(e.text||'').replace(/^\d+月\d+日 周. \d\d:\d\d /,'');
    html+='<div style="padding:5px 0;border-bottom:1px solid #1a1f28"><span style="color:#64748b;font-size:12px">'+hh+':'+mm+'</span> '+
      '<span style="color:'+color+';font-size:11px;border:1px solid '+color+'55;border-radius:6px;padding:0 5px;margin-right:6px">'+tag+'</span>'+text+'</div>';
  });
  el('world_events').innerHTML=html||'这一天还没有事件';
}
async function loadWorldEvents(day){
  try{
    const r=await fetch(B+'/api/world/events?day_index='+encodeURIComponent(day)).then(x=>x.json());
    if(r.code!==0) return;
    renderWorldEvents(r.events||[]);
    fillWorldDays(r.days||[], r.day_index||0);
  }catch(e){}
}
async function refreshWeather(){
  el('world_weather').textContent='定位中…';
  try{
    const r=await fetch(B+'/api/weather?refresh=1').then(x=>x.json());
    const w=r.weather||{};
    el('world_weather').textContent=w.city?((w.city+(w.district||''))+'　'+(w.text||'')+'　气温 '+(w.temp??'-')+'℃'):'还没定位到，登录一次后台或用手机定位';
  }catch(e){ el('world_weather').textContent='天气获取失败'; }
}
function locateWeather(){
  if(!navigator.geolocation){ el('world_weather').textContent='当前浏览器不支持定位'; return; }
  el('world_weather').textContent='正在获取定位…';
  navigator.geolocation.getCurrentPosition(async function(pos){
    try{
      const r=await fetch(B+'/api/weather/loc',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({lat:pos.coords.latitude, lon:pos.coords.longitude})}).then(x=>x.json());
      const w=r.weather||{};
      el('world_weather').textContent='已保存：'+(r.city||w.city||'')+(r.district||w.district||'')+'　'+(w.text||'')+'　气温 '+(w.temp??'-')+'℃';
    }catch(e){ el('world_weather').textContent='定位保存失败'; }
  }, function(){ el('world_weather').textContent='定位被拒绝，可继续用 IP 定位'; }, {timeout:10000});
}
async function saveWorldJob(){
  const job=el('world_job').value.trim();
  const salary=parseInt(el('world_salary').value||'0');
  const r=await fetch(B+'/api/world/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job:job,salary:salary})}).then(x=>x.json());
  el('world_check').textContent=r.code===0?'已保存，身份卡刷新中…':(r.message||'保存失败');
  if(r.code===0) setTimeout(loadWorld,1200);
}
async function worldToggle(){
  const r=await fetch(B+'/api/world/state').then(x=>x.json());
  const on=String((r.state||{}).enabled)==='1';
  await fetch(B+'/api/world/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!on})});
  loadWorld();
}
async function worldTogglePhoto(){
  const r=await fetch(B+'/api/world/state').then(x=>x.json());
  const on=String((r.state||{}).photo_enabled)==='1';
  await fetch(B+'/api/world/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({photo_enabled:!on})});
  loadWorld();
}
async function savePhotoMax(){
  const n=parseInt(el('world_photo_max').value||'3');
  const r=await fetch(B+'/api/world/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({photo_max:n})}).then(x=>x.json());
  el('world_check').textContent=r.code===0?'已保存，每天最多 '+n+' 张':(r.message||'保存失败');
}
async function saveShareMax(){
  const n=parseInt(el('world_share_max').value||'3');
  const r=await fetch(B+'/api/world/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({share_max:n})}).then(x=>x.json());
  el('world_check').textContent=r.code===0?'已保存，每天最多 '+n+' 条':(r.message||'保存失败');
}
async function worldToggleGreet(){
  const r=await fetch(B+'/api/world/state').then(x=>x.json());
  const on=String((r.state||{}).greetings)==='1';
  await fetch(B+'/api/world/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({greetings:!on})});
  loadWorld();
}
async function worldToggleProactive(){
  const r=await fetch(B+'/api/world/state').then(x=>x.json());
  const on=String((r.state||{}).proactive)==='1';
  await fetch(B+'/api/world/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proactive:!on})});
  loadWorld();
}
async function worldCheck(){
  const r=await fetch(B+'/api/world/check').then(x=>x.json());
  el('world_check').textContent=r.issues.length?('发现问题：'+r.issues.join('；')):'状态一致，没有发现问题';
}
let RCL = {enabled:true, echo_group:false};
const TOK_KIND = {chat:'对话回复', complete:'记忆等辅助', game:'剧本游戏', judge:'是否回复判定',
                  sticker:'表情包识别', roast:'互怼', bored:'无聊搭话', notice:'休息公告'};
let TOK_RANGE = 'today';
function tokNum(n){ n = Number(n)||0; return n.toLocaleString('en-US'); }
function tokRange(r, node){
  TOK_RANGE = r;
  const bar = el('tokranges');
  if(bar) bar.querySelectorAll('.tab').forEach(function(x){ x.classList.toggle('on', x === node); });
  loadTokens();
}
function tokTable(headers, rows){
  if(!rows.length) return '<div class="hint">暂无数据</div>';
  let h = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
  h += '<thead><tr>' + headers.map(function(x){
    return '<th style="text-align:left;padding:6px 8px;color:#8b93a5;font-weight:400;border-bottom:1px solid #242833">'+x+'</th>';
  }).join('') + '</tr></thead><tbody>';
  rows.forEach(function(cells){
    h += '<tr>' + cells.map(function(c){
      return '<td style="padding:6px 8px;border-bottom:1px solid #1b1f27">'+c+'</td>';
    }).join('') + '</tr>';
  });
  return h + '</tbody></table>';
}
async function loadTokens(){
  const s = el('toksum');
  if(s) s.textContent = '加载中…';
  try{
    const r = await fetch(B + '/api/tokens?range=' + encodeURIComponent(TOK_RANGE)).then(function(x){ return x.json(); });
    if(r.code !== 0){ if(s) s.textContent = r.message || '加载失败'; return; }
    const d = r.summary || {};
    if(el('toklabel')) el('toklabel').textContent = r.label || '';
    if(el('tokspan')) el('tokspan').textContent = r.start ? (r.start + (r.end && r.end !== r.start ? ' ~ ' + r.end : '')) : '全部时间';
    if(s) s.innerHTML =
      '<div style="display:flex;gap:22px;flex-wrap:wrap">' +
      '<div><div style="font-size:12px;color:#6b7280">调用次数</div><div style="font-size:20px">' + tokNum(d.calls) + '</div></div>' +
      '<div><div style="font-size:12px;color:#6b7280">输入 tokens</div><div style="font-size:20px">' + tokNum(d.prompt) + '</div></div>' +
      '<div><div style="font-size:12px;color:#6b7280">输出 tokens</div><div style="font-size:20px">' + tokNum(d.completion) + '</div></div>' +
      '<div><div style="font-size:12px;color:#6b7280">合计</div><div style="font-size:20px;color:#7dd3fc">' + tokNum(d.total) + '</div></div>' +
      '</div>';
    el('tokdays').innerHTML = tokTable(['日期','调用','输入','输出','合计'],
      (r.days||[]).map(function(x){ return [x.day, tokNum(x.calls), tokNum(x.prompt), tokNum(x.completion), tokNum(x.total)]; }));
    el('tokkinds').innerHTML = tokTable(['类型','调用','合计'],
      (r.kinds||[]).map(function(x){ return [TOK_KIND[x.kind] || x.kind || '未知', tokNum(x.calls), tokNum(x.total)]; }));
    el('tokrecent').innerHTML = tokTable(['时间','类型','输入','输出','合计'],
      (r.recent||[]).map(function(x){ return [x.ts, TOK_KIND[x.kind] || x.kind || '', tokNum(x.prompt), tokNum(x.completion), tokNum(x.total)]; }));
  }catch(e){ if(s) s.textContent = '加载失败：' + e; }
}
let TM = {enabled:false, qq:''};
function tmPaint(){
  const b = el('tm_btn'); if(!b) return;
  b.textContent = '测试模式：' + (TM.enabled ? '已开启' : '已关闭');
  b.style.background = TM.enabled ? '#16a34a' : '#374151';
  b.style.color = '#fff'; b.style.border = '0';
}
async function loadTestMode(){
  try{
    const r = await fetch(B + '/api/testmode').then(function(x){ return x.json(); });
    if(r.code !== 0){ el('tm_msg').textContent = r.message || '加载失败'; return; }
    TM = {enabled: !!r.enabled, qq: r.qq || ''};
    el('tm_qq').value = r.qq || '';
    tmPaint();
    el('tm_target').textContent = '当前转发目标：' + (r.target || '（未设置）');
  }catch(e){ el('tm_msg').textContent = '加载失败：' + e; }
}
async function toggleTestMode(){ TM.enabled = !TM.enabled; tmPaint(); await saveTestMode(); }
async function saveTestMode(){
  try{
    const r = await fetch(B + '/api/testmode', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({enabled: TM.enabled, qq: (el('tm_qq').value || '').trim()})}).then(function(x){ return x.json(); });
    el('tm_msg').textContent = r.code === 0 ? '已保存' : (r.message || '保存失败');
    if(r.code === 0){
      TM.enabled = !!r.enabled; TM.qq = r.qq || ''; tmPaint();
      el('tm_target').textContent = '当前转发目标：' + (r.target || '（未设置）');
    }
  }catch(e){ el('tm_msg').textContent = '保存失败：' + e; }
}
let SC_LAST = null;
function copySelfCheckReport(){
  if(!SC_LAST && !FC_LAST){ return; }
  const NL = String.fromCharCode(10);
  const now = new Date();
  const pad = function(n){ return (n<10?'0':'')+n; };
  const ts = now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate())+' '+pad(now.getHours())+':'+pad(now.getMinutes());
  const lines = [];
  lines.push('FishPond 自检报告 v'+((SC_LAST&&SC_LAST.version)||(FC_LAST&&FC_LAST.version)||'?')+'  '+ts);
  if(SC_LAST){
    const r = SC_LAST;
    let head = '[接口] 共 '+r.total+' 项 / 通过 '+r.passed+' / 失败 '+r.failed;
    if(r.route_total){ head += '（全站 '+r.route_total+' 个路由，其余为写操作，未自动测试）'; }
    lines.push(head);
    const bad = (r.items||[]).filter(function(x){ return !x.ok; });
    bad.forEach(function(x){ lines.push('  ✗ '+(x.method||'GET')+' '+x.path+'  HTTP '+x.status+'  '+(x.msg||'')); });
    if(!bad.length){ lines.push('  全部通过'); }
  }
  if(FC_LAST){
    const f = FC_LAST;
    lines.push('[功能] 共 '+f.total+' 项 / 通过 '+f.passed+' / 失败 '+f.failed);
    const badf = (f.items||[]).filter(function(x){ return !x.ok; });
    badf.forEach(function(x){ lines.push('  ✗ ['+x.group+'] '+x.name+'  '+(x.msg||'')); });
    if(!badf.length){ lines.push('  全部通过'); }
  }
  const t = lines.join(NL);
  const btn = el('sc_copy');
  navigator.clipboard.writeText(t).then(function(){
    if(btn){ btn.textContent = '已复制'; setTimeout(function(){ btn.textContent = '复制报告'; }, 1500); }
  }).catch(function(){
    const w = window.open('');
    if(w){ w.document.write('<pre style="white-space:pre-wrap;font:13px monospace">'+t.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</pre>'); }
  });
}
let FC_LAST = null;
async function runFeatureCheck(){
  const btn = el('fc_btn');
  btn.disabled = true; btn.textContent = '自检中…';
  el('fc_sum').textContent = '';
  el('fc_result').textContent = '正在逐项验证功能（约 10~40 秒）…';
  try{
    const r = await fetch(B + '/api/featurecheck/run', {method:'POST', headers:{'Content-Type':'application/json'},
      body: '{}'}).then(function(x){ return x.json(); });
    if(r.code !== 0){ el('fc_result').textContent = r.message || '自检失败'; return; }
    let html = '<table style="width:100%;border-collapse:collapse;font-size:13px"><tbody>';
    let last = '';
    (r.items || []).forEach(function(x){
      if(x.group !== last){
        last = x.group;
        html += '<tr><td colspan="4" style="padding:10px 8px 4px;color:#8b93a5">' + x.group + '</td></tr>';
      }
      const col = x.ok ? '#4ade80' : '#f87171';
      html += '<tr>' +
        '<td style="padding:4px 8px">' + x.name + '</td>' +
        '<td style="padding:4px 8px;color:' + col + '">' + (x.ok ? '通过' : '失败') + '</td>' +
        '<td style="padding:4px 8px;color:#6b7280">' + x.ms + 'ms</td>' +
        '<td style="padding:4px 8px;color:' + (x.ok ? '#6b7280' : '#f87171') + '">' + (x.msg || '') + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
    el('fc_result').innerHTML = html;
    FC_LAST = r;
    const c = el('sc_copy'); if(c) c.style.display = '';
    el('fc_sum').textContent = '共 ' + r.total + ' 项，通过 ' + r.passed + '，失败 ' + r.failed;
  }catch(e){ el('fc_result').textContent = '自检失败：' + e; }
  finally{ btn.disabled = false; btn.textContent = '开始功能自检'; }
}
async function runSelfCheck(){
  const btn = el('sc_btn');
  btn.disabled = true; btn.textContent = '自检中…';
  el('sc_sum').textContent = '';
  el('sc_result').textContent = '正在逐个调用接口（约 10~30 秒）…';
  try{
    const r = await fetch(B + '/api/selfcheck/run', {method:'POST', headers:{'Content-Type':'application/json'},
      body: '{}'}).then(function(x){ return x.json(); });
    if(r.code !== 0){ el('sc_result').textContent = r.message || '自检失败'; return; }
    let html = '<table style="width:100%;border-collapse:collapse;font-size:13px"><tbody>';
    let last = '';
    (r.items || []).forEach(function(x){
      if(x.group !== last){
        last = x.group;
        html += '<tr><td colspan="4" style="padding:10px 8px 4px;color:#8b93a5">' + x.group + '</td></tr>';
      }
      const col = x.ok ? '#4ade80' : '#f87171';
      html += '<tr>' +
        '<td style="padding:4px 8px">' + x.path + '</td>' +
        '<td style="padding:4px 8px;color:' + col + '">' + (x.ok ? '通过' : (x.status || 'ERR')) + '</td>' +
        '<td style="padding:4px 8px;color:#6b7280">' + x.ms + 'ms</td>' +
        '<td style="padding:4px 8px;color:#f87171">' + (x.msg || '') + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
    el('sc_result').innerHTML = html;
    SC_LAST = r;
    const cbtn = el('sc_copy'); if(cbtn) cbtn.style.display = '';
    el('sc_sum').textContent = '共 ' + r.total + ' 个，通过 ' + r.passed + '，失败 ' + r.failed + (r.route_total ? ('（全站 ' + r.route_total + ' 个路由）') : '');
  }catch(e){ el('sc_result').textContent = '自检失败：' + e; }
  finally{ btn.disabled = false; btn.textContent = '开始自检'; }
}
function rclPaint(){
  const set=function(id,on){ const b=el(id); if(!b) return; b.textContent = on?'已开启':'已关闭';
    b.style.background=on?'#16a34a':'#374151'; b.style.color='#fff'; b.style.border='0'; };
  set('rcl_en', !!RCL.enabled); set('rcl_echo', !!RCL.echo_group);
}
function rclToggle(k){ RCL[k]=!RCL[k]; rclPaint(); }
async function loadRecall(){
  try{
    const r=await fetch(B+'/api/recall/config').then(x=>x.json());
    if(r.code!==0){ el('rclmsg').textContent=r.message||'加载失败'; return; }
    RCL={enabled:!!r.enabled, echo_group:!!r.echo_group};
    el('rcl_start').value=(r.start||'00:00').slice(0,5);
    el('rcl_end').value=(r.end||'23:59').slice(0,5);
    rclPaint();
    el('rclmsg').textContent='';
  }catch(e){ el('rclmsg').textContent='加载失败：'+e; }
}
async function saveRecall(){
  const m=el('rclmsg');
  try{
    const r=await fetch(B+'/api/recall/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enabled:RCL.enabled, echo_group:RCL.echo_group,
        start:el('rcl_start').value||'00:00', end:el('rcl_end').value||'23:59'})}).then(x=>x.json());
    m.textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
    m.style.color = r.code===0 ? '#4ade80' : '#f87171';
  }catch(e){ m.textContent='保存失败：'+e; m.style.color='#f87171'; }
}
let GM = {};
let CUR_GID = "";
let GM_GROUPS = [];
function gmLink(token){ return location.origin + location.pathname.replace(/\/$/, '') + '/g/' + token + '/'; }
async function loadGMGroups(){
  try{
    const r = await fetch(B + '/api/gm/groups').then(x=>x.json());
    GM_GROUPS = (r.items || []);
  }catch(e){ GM_GROUPS = []; }
  gmRenderTabs();
  gmRenderPanel();
}
function gmRenderTabs(){
  const bar = el('gmtabs'); if(!bar) return;
  bar.innerHTML = '';
  const mk = function(label, fn, on){
    const d = document.createElement('div');
    d.className = 'tab' + (on ? ' on' : '');
    d.textContent = label; d.onclick = fn; bar.appendChild(d);
  };
  mk('群面板', function(){ CUR_GID=''; loadGM(); }, !CUR_GID);
  GM_GROUPS.forEach(function(g){
    mk(g.group_id, function(){ CUR_GID = g.group_id; loadGM(); }, CUR_GID === g.group_id);
  });
}
function gmRenderPanel(){
  const tb = el('gmp_body'); if(!tb) return;
  tb.innerHTML = GM_GROUPS.map(function(g){
    const link = gmLink(g.token || '');
    const on = int(g.enabled) !== 0;
    return '<tr style="border-top:1px solid #1f242e">' +
      '<td style="padding:6px">' + g.group_id + '</td>' +
      '<td style="padding:6px"><input style="text-align:center;min-width:130px" id="gmu_' + g.group_id + '" value="' + (g.username||'') + '" style="width:110px"></td>' +
      '<td style="padding:6px"><input id="gmp_' + g.group_id + '" value="" placeholder="留空不修改" style="width:120px"></td>' +
      '<td style="padding:6px">' + (on?'已开启':'已停用') + '</td>' +
      '<td style="padding:6px"><a href="' + link + '" target="_blank" style="color:#60a5fa">打开</a> ' +
      '<button onclick="gmCopy(&#39;' + link + '&#39;)">复制</button></td>' +
      '<td style="padding:6px"><button onclick="gmSaveAccount(&#39;' + g.group_id + '&#39;)">保存</button> ' +
      '<button onclick="gmReset(&#39;' + g.group_id + '&#39;)">重置密码</button> ' +
      '<button onclick="gmLogin(&#39;' + g.group_id + '&#39;)">登录</button> ' +
      '<button onclick="gmGroupOp(&#39;' + g.group_id + '&#39;,&#39;toggle&#39;)">' + (on?'停用':'启用') + '</button> ' +
      '<button onclick="gmGroupOp(&#39;' + g.group_id + '&#39;,&#39;delete&#39;)">删除</button></td></tr>';
  }).join('');
}
function int(v){ return parseInt(v||'0',10) || 0; }
function gmCopy(t){ navigator.clipboard && navigator.clipboard.writeText(t); }
async function gmSaveAccount(gid){
  const u = el('gmu_' + gid).value.trim(), p = el('gmp_' + gid).value.trim();
  if(!p && !confirm('密码留空表示不修改，继续？')) return;
  const r = await fetch(B + '/api/gm/groups',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'save', group_id:gid, username:u, password:p})}).then(x=>x.json());
  if(r.code!==0) alert(r.message||'保存失败');
  loadGMGroups();
}
async function gmLogin(gid){
  const r = await fetch(B + '/api/gm/groups',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'login_link', group_id:gid})}).then(x=>x.json());
  if(r.code!==0){ alert(r.message||'生成登录链接失败'); return; }
  window.open(location.origin + r.path, '_blank');
}
async function gmReset(gid){
  if(!confirm('重置该群面板密码？新密码只显示这一次')) return;
  const r = await fetch(B + '/api/gm/groups',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'reset', group_id:gid})}).then(x=>x.json());
  if(r.code===0) alert('新密码：' + r.password + '\n账号：' + r.username + '\n请立即保存');
  else alert(r.message||'重置失败');
  loadGMGroups();
}
async function gmGroupCreate(){
  const gid = el('gmp_gid').value.trim();
  if(!/^[0-9]{5,12}$/.test(gid)){ el('gmp_msg').textContent='群号无效'; return; }
  const r = await fetch(B + '/api/gm/groups',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'create', group_id:gid, username:el('gmp_user').value.trim(), password:el('gmp_pass').value.trim()})}).then(x=>x.json());
  el('gmp_msg').textContent = r.code===0 ? ('已创建：' + r.username + ' / ' + r.password) : (r.message||'失败');
  el('gmp_msg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  loadGMGroups();
}
async function gmGroupOp(gid, act){
  if(act==='delete' && !confirm('删除群面板？配置会一起删除')) return;
  const r = await fetch(B + '/api/gm/groups',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:act, group_id:gid})}).then(x=>x.json());
  if(r.code!==0) alert(r.message||'失败');
  loadGMGroups();
}
function gmPaint(){
  [['gm_auto_btn','gm_auto_approve'],['gm_verify_btn','gm_verify'],['gm_kick_btn','gm_kick_enabled'],['gm_blk_btn','gm_blacklist_kick'],['gm_mute_btn','gm_mute_enabled'],['gm_patrol_btn','gm_patrol_enabled'],['gm_ai_btn','gm_ai_patrol'],['gm_silent_btn','gm_silent'],['gm_recall_btn','gm_recall_enabled']].forEach(function(p){
    const b = el(p[0]); if(!b) return; const on = GM[p[1]] === '1';
    b.textContent = b.textContent.split('：')[0] + '：' + (on ? '已开启' : '已关闭');
    b.style.background = on ? '#16a34a' : '#374151'; b.style.color = '#fff'; b.style.border = '0';
  });
}
function gmToggle(k){
  GM[k] = (GM[k] === '1') ? '0' : '1';
  if (GM[k] === '1') {
    if (k === 'gm_kick_enabled') GM.gm_blacklist_kick = '0';
    if (k === 'gm_blacklist_kick') GM.gm_kick_enabled = '0';
  }
  gmPaint();
}
async function loadGM(){
  document.querySelectorAll('#gm > .card').forEach(function(c){
    if(c.id === 'gm_panel'){ c.style.display = CUR_GID ? 'none' : 'block'; }
    else { c.style.display = CUR_GID ? 'block' : 'none'; }
  });
  gmRenderTabs();
  if(!CUR_GID) return;
  try{
    const r = await fetch(B + '/api/gm/config?gid=' + encodeURIComponent(CUR_GID)).then(x=>x.json());
    if(r.code !== 0){ el('gmmsg').textContent = r.message || '加载失败'; return; }
    GM = r;
    el('gm_groups').value = r.gm_groups || '';
    el('gm_welcome').value = r.gm_welcome || '';
    QLIST = String(r.gm_questions || '').split(String.fromCharCode(10)).map(function(line){
      const m = line.split('|');
      return {q: (m[0] || '').trim(), a: (m[1] || '').trim()};
    }).filter(function(x){ return x.q || x.a; });
    qRender();
    el('gm_timeout_min').value = r.gm_timeout_min || 5;
    el('gm_patrol_rate').value = r.gm_patrol_rate || 10;
    el('gm_patrol_mute_min').value = r.gm_patrol_mute_min || 10;
    el('gm_patrol_warn').value = r.gm_patrol_warn || '';
    el('gm_ai_context').value = r.gm_ai_context || 6;
    el('gm_ai_action').value = r.gm_ai_action || 'warn';
    el('gm_kick_keywords').value = r.gm_kick_keywords || '踢';
    el('gm_blacklist_keywords').value = r.gm_blacklist_keywords || '';
    el('gm_recall_keywords').value = r.gm_recall_keywords || '';
    KLIST = String(r.gm_kwlimit_rules || '').split(String.fromCharCode(10)).map(function(line){
      const m = line.split('|'); return {k:(m[0]||'').trim(), w:(m[1]||'60').trim(), n:(m[2]||'1').trim()};
    }).filter(function(x){ return x.k; });
    klRender();
    el('gm_kick_qqs').value = r.gm_kick_qqs || '';
    el('gm_punish_qqs').value = r.gm_punish_qqs || '';
    el('gm_verify_mode').value = r.gm_verify_mode || 'private';
    gmPaint(); el('gmmsg').textContent = '';
    loadBL();
  }catch(e){ el('gmmsg').textContent = '加载失败：' + e; }
}
async function saveGM(){
  qCollect();
  const body = {gid:CUR_GID, gm_groups:el('gm_groups').value, gm_welcome:el('gm_welcome').value,
    gm_questions:QLIST.filter(function(x){return x.q && x.a;}).map(function(x){return x.q + '|' + x.a;}).join(String.fromCharCode(10)),
    gm_timeout_min:el('gm_timeout_min').value, gm_kick_qqs:el('gm_kick_qqs').value, gm_punish_qqs:el('gm_punish_qqs').value,
    gm_verify_mode:el('gm_verify_mode').value,
    gm_auto_approve:GM.gm_auto_approve||'0', gm_verify:GM.gm_verify||'0',
    gm_kick_enabled:GM.gm_kick_enabled||'0', gm_blacklist_kick:GM.gm_blacklist_kick||'0',
    gm_mute_enabled:GM.gm_mute_enabled||'0', gm_silent:GM.gm_silent||'0',
    gm_patrol_enabled:GM.gm_patrol_enabled||'0', gm_ai_patrol:GM.gm_ai_patrol||'0',
    gm_patrol_rate:el('gm_patrol_rate').value, gm_patrol_mute_min:el('gm_patrol_mute_min').value,
    gm_patrol_warn:el('gm_patrol_warn').value, gm_ai_context:el('gm_ai_context').value,
    gm_ai_action:el('gm_ai_action').value,
    gm_kick_keywords:el('gm_kick_keywords').value, gm_blacklist_keywords:el('gm_blacklist_keywords').value,
    gm_recall_keywords:el('gm_recall_keywords').value, gm_recall_enabled:GM.gm_recall_enabled||'0',
    gm_kwlimit_rules:(function(){ klCollect(); return KLIST.filter(function(x){return x.k;}).map(function(x){return x.k + '|' + x.w + '|' + x.n;}).join(String.fromCharCode(10)); })()};
  const r = await fetch(B + '/api/gm/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)}).then(x=>x.json());
  const okMsg = r.code === 0 ? '已保存' : (r.message || '保存失败');
  el('gmmsg').textContent = okMsg;
  el('gmmsg').style.color = r.code === 0 ? '#4ade80' : '#f87171';
  ['gmpmsg','gmkmsg'].forEach(function(id){
    if(el(id)){ el(id).textContent = okMsg; el(id).style.color = el('gmmsg').style.color; }
  });
}
let QLIST = [];
function paintT(){
 const box=document.getElementById('toggles'); if(!box)return;
 box.innerHTML=BOOLS.map(k=>'<button onclick="tog(&#39;'+k+'&#39;)" style="background:'+(ST[k]?'#16a34a':'#374151')+'">'+BNAMES[k]+'：'+(ST[k]?'已开启':'已关闭')+'</button>').join('');
}
function tog(k){ ST[k]=!ST[k]; paintT(); }
function qRender(){
  const tb = el('q_body'); if(!tb) return;
  tb.innerHTML = QLIST.map(function(it, i){
    return '<tr style="border-top:1px solid #1f242e">' +
      '<td style="padding:6px">' + (i + 1) + '</td>' +
      '<td style="padding:6px"><input class="qin" data-i="' + i + '" data-k="q" oninput="qSet(this)" value="' + String(it.q || '').replace(/"/g, '&quot;') + '" style="width:100%;box-sizing:border-box"></td>' +
      '<td style="padding:6px"><input class="ain" data-i="' + i + '" data-k="a" oninput="qSet(this)" value="' + String(it.a || '').replace(/"/g, '&quot;') + '" style="width:100%;box-sizing:border-box"></td>' +
      '<td style="padding:6px"><button onclick="qDel(' + i + ')">删除</button></td></tr>';
  }).join('');
}
function qSet(inp){ const it = QLIST[+inp.dataset.i]; if(it) it[inp.dataset.k] = inp.value; }
function qAdd(){ qCollect(); QLIST.push({q:'', a:''}); qRender(); }
function qDel(i){ qCollect(); QLIST.splice(i, 1); qRender(); }
function qCollect(){
  const rows = Array.prototype.slice.call(document.querySelectorAll('#q_body tr'));
  QLIST = rows.map(function(tr){
    const q = tr.querySelector('.qin'), a = tr.querySelector('.ain');
    return {q: q ? q.value : '', a: a ? a.value : ''};
  });
}
let KLIST = [];
function klRender(){
  const tb = el('kl_body'); if(!tb) return;
  tb.innerHTML = KLIST.map(function(it, i){
    return '<tr style="border-top:1px solid #1f242e">' +
      '<td style="padding:6px">' + (i + 1) + '</td>' +
      '<td style="padding:6px"><input class="kin" data-k="k" value="' + String(it.k || '').replace(/"/g, '&quot;') + '" style="width:100%;box-sizing:border-box"></td>' +
      '<td style="padding:6px"><input class="kin" data-k="w" type="number" min="1" value="' + String(it.w || '60') + '" style="width:100%;box-sizing:border-box"></td>' +
      '<td style="padding:6px"><input class="kin" data-k="n" type="number" min="1" value="' + String(it.n || '1') + '" style="width:100%;box-sizing:border-box"></td>' +
      '<td style="padding:6px"><button onclick="klDel(' + i + ')">删除</button></td></tr>';
  }).join('');
}
function klCollect(){
  const rows = Array.prototype.slice.call(document.querySelectorAll('#kl_body tr'));
  KLIST = rows.map(function(tr){
    const ins = tr.querySelectorAll('.kin'); const o = {};
    ins.forEach(function(x){ o[x.dataset.k] = x.value; });
    return {k: o.k || '', w: o.w || '60', n: o.n || '1'};
  });
}
function klAdd(){ klCollect(); KLIST.push({k:'', w:'60', n:'1'}); klRender(); }
function klDel(i){ klCollect(); KLIST.splice(i, 1); klRender(); }
function qRowsText(){
  const rows = Array.prototype.slice.call(document.querySelectorAll('#q_body tr'));
  return rows.map(function(tr){
    const q = tr.querySelector('.qin'), a = tr.querySelector('.ain');
    return {q: q ? q.value.trim() : '', a: a ? a.value.trim() : ''};
  }).filter(function(x){ return x.q || x.a; });
}
async function saveQuestions(){
  const list = qRowsText().filter(function(x){ return x.q && x.a; });
  const text = list.map(function(x){ return x.q + '|' + x.a; }).join(String.fromCharCode(10));
  const m = el('qmsg'); m.textContent = '保存中…'; m.style.color = '#9aa4b8';
  try{
    const r = await fetch(B + '/api/gm/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({gm_questions:text})}).then(x=>x.json());
    m.textContent = r.code === 0 ? ('已保存 ' + list.length + ' 题') : (r.message || '保存失败');
    m.style.color = r.code === 0 ? '#4ade80' : '#f87171';
  }catch(e){ m.textContent = '保存失败：' + e; m.style.color = '#f87171'; }
}
async function loadBL(){
  try{
    const r = await fetch(B + '/api/gm/blacklist').then(x=>x.json());
    const tb = el('bl_body'); if(!tb) return;
    if(r.code !== 0){ tb.innerHTML = ''; return; }
    tb.innerHTML = (r.items || []).map(function(it){
      const qq = String(it.qq || '');
      const nick = String(it.nick || '');
      const av = 'https://q1.qlogo.cn/g?b=qq&nk=' + encodeURIComponent(qq) + '&s=100';
      return '<tr style="border-top:1px solid #1f242e">' +
        '<td style="padding:6px"><img src="' + av + '" style="width:32px;height:32px;border-radius:50%" loading="lazy"></td>' +
        '<td style="padding:6px">' + qq + '</td>' +
        '<td style="padding:6px">' + nick + '</td>' +
        '<td style="padding:6px"><button onclick="blEdit(&#39;' + qq + '&#39;)">修改</button> ' +
        '<button onclick="blRemove(&#39;' + qq + '&#39;)">移除</button></td></tr>';
    }).join('');
  }catch(e){}
}
async function blAdd(){
  const qq = el('bl_qq').value.trim(), nick = el('bl_nick').value.trim();
  if(!/^[0-9]{5,12}$/.test(qq)){ el('blmsg').textContent = 'QQ 号无效'; return; }
  const r = await fetch(B + '/api/gm/blacklist',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'add', qq:qq, nick:nick})}).then(x=>x.json());
  el('blmsg').textContent = r.code === 0 ? '已保存' : (r.message || '失败');
  el('blmsg').style.color = r.code === 0 ? '#4ade80' : '#f87171';
  el('bl_qq').value = ''; el('bl_nick').value = ''; loadBL();
}
async function blEdit(qq){
  const nick = prompt('修改 ' + qq + ' 的昵称：');
  if(nick === null) return;
  const r = await fetch(B + '/api/gm/blacklist',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'update', old_qq:qq, qq:qq, nick:nick})}).then(x=>x.json());
  if(r.code !== 0) alert(r.message || '修改失败');
  loadBL();
}
async function blRemove(qq){
  if(!confirm('确定把 ' + qq + ' 移出黑名单？')) return;
  const r = await fetch(B + '/api/gm/blacklist',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'remove', qq:qq})}).then(x=>x.json());
  if(r.code !== 0) alert(r.message || '移除失败');
  loadBL();
}
let BILI={};
function biliPaint(){
  const set=function(id,on,label){const b=el(id);if(!b)return;b.textContent=label+(on?'：已开启':'：已关闭');b.style.background=on?'#16a34a':'#374151';b.style.color='#fff';b.style.border='0';};
  set('bili_en',BILI.bili_enabled==='1','B站功能');
  set('bili_all',BILI.bili_allow_all==='1','所有人可用');
  set('bili_auto_en',BILI.bili_auto_enabled==='1','AI 自动学习');
  set('bili_share',BILI.bili_share_super==='1','分享给超管');
  set('bili_pro',BILI.bili_proactive_enabled==='1','主动找话题');
}
async function loadBili(){
  try{
    const r=await fetch(B+'/api/bili/config').then(x=>x.json());
    if(r.code!==0){el('bilimsg').textContent=r.message||'加载失败';return;}
    BILI={bili_enabled:r.bili_enabled,bili_allow_all:r.bili_allow_all,bili_auto_enabled:r.bili_auto_enabled,bili_share_super:r.bili_share_super,bili_proactive_enabled:r.bili_proactive_enabled};
    el('bili_count').value=r.bili_count||3;
    el('bili_auto_start').value=(r.bili_auto_start||'05:00').slice(0,5);
    el('bili_auto_end').value=(r.bili_auto_end||'07:00').slice(0,5);
    el('bili_auto_topics').value=r.bili_auto_topics||'';
    el('bili_auto_max').value=r.bili_auto_max||3;
    el('bili_auto_group').value=r.bili_auto_group||'';
    el('bili_pro_min').value=r.bili_proactive_min_mem||5;
    biliPaint();el('bilimsg').textContent='';
  }catch(e){el('bilimsg').textContent='加载失败：'+e;}
}
function biliToggle(k){BILI[k]=BILI[k]==='1'?'0':'1';biliPaint();}
async function saveBili(){
  const r=await fetch(B+'/api/bili/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({bili_enabled:BILI.bili_enabled||'1',bili_allow_all:BILI.bili_allow_all||'0',
      bili_count:el('bili_count').value, bili_auto_enabled:BILI.bili_auto_enabled||'0',
      bili_auto_start:el('bili_auto_start').value||'05:00', bili_auto_end:el('bili_auto_end').value||'07:00',
      bili_auto_topics:el('bili_auto_topics').value, bili_auto_max:el('bili_auto_max').value,
      bili_auto_group:el('bili_auto_group').value,
      bili_share_super:BILI.bili_share_super||'1',
      bili_proactive_enabled:BILI.bili_proactive_enabled||'0', bili_proactive_min_mem:el('bili_pro_min').value})}).then(x=>x.json());
  el('bilimsg').textContent=r.code===0?'已保存':(r.message||'保存失败');
  el('bilimsg').style.color=r.code===0?'#4ade80':'#f87171';
}
async function biliAcctLoad(){
  try{
    const r=await fetch(B+'/api/bili/account/status').then(x=>x.json());
    const a=r.account||{};
    el('biliacct_status').textContent=a.uid?('已登录：'+(a.uname||a.uid)+'（今天评论'+a.comments+'/点赞'+a.likes+'）'):'未登录';
    if(!el('biliacct_mid').value) el('biliacct_mid').value=a.super_mid||'';
    if(!el('biliacct_uname').value) el('biliacct_uname').value=a.super_uname||'';
    if(!el('biliacct_cmax').value) el('biliacct_cmax').value=a.comment_max||2;
    if(!el('biliacct_lmax').value) el('biliacct_lmax').value=a.like_max||8;
    el('biliacct_cdone').textContent=a.comments||0;
    el('biliacct_ldone').textContent=a.likes||0;
    el('biliacct_ddone').textContent=a.dms||0;
    el('biliacct_risk').textContent=a.risk?a.risk.slice(0,60):'无';
    biliAcctLogs();
  }catch(e){}
}
async function biliAcctQr(force){
  el('biliacct_msg').textContent=force?'刷新二维码…':'生成二维码…';
  try{
    const r=await fetch(B+'/api/bili/account/qr'+(force?'?refresh=1':'')).then(x=>x.json());
    if(r.code!==0){ el('biliacct_msg').textContent=r.message||'失败'; return; }
    el('biliacct_qr').src=r.image; el('biliacct_qrbox').style.display='block';
    el('biliacct_msg').textContent='用 B 站 App 扫码并确认，页面会自动检测…';
    let n=0;
    if(window.__biliQrTimer) clearInterval(window.__biliQrTimer);
    window.__biliQrTimer=setInterval(async function(){
      n++;
      if(n>90){ clearInterval(window.__biliQrTimer); el('biliacct_msg').textContent='二维码超时，请重新扫码'; return; }
      try{
        const p=await fetch(B+'/api/bili/account/qr/poll').then(x=>x.json());
        if(p.code!==0) return;
        if(p.state==='done'){
          clearInterval(window.__biliQrTimer);
          el('biliacct_msg').textContent='登录成功：'+(p.uname||p.uid);
          el('biliacct_msg').style.color='#4ade80';
          el('biliacct_qrbox').style.display='none';
          biliAcctLoad();
        } else if(p.state==='scan'){
          el('biliacct_msg').textContent='已扫码，请在手机 B 站点「确认登录」';
        } else if(p.state==='confirm'){
          el('biliacct_msg').textContent='已扫码，等待确认…';
        } else if(p.state==='timeout'){
          clearInterval(window.__biliQrTimer);
          el('biliacct_msg').textContent='二维码超时，请重新扫码';
        }
      }catch(e){}
    },2000);
  }catch(e){ el('biliacct_msg').textContent='网络错误'; }
}
async function biliAcctCookies(){
  el('biliacct_msg').textContent='校验 Cookie…';
  try{
    const r=await fetch(B+'/api/bili/account/cookies',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sessdata:el('biliacct_sess').value.trim(), bili_jct:el('biliacct_jct').value.trim(), uid:el('biliacct_uid').value.trim()})}).then(x=>x.json());
    el('biliacct_msg').textContent=r.code===0?('登录成功：'+(r.uname||r.uid)):(r.message||'失败');
    el('biliacct_msg').style.color=r.code===0?'#4ade80':'#f87171';
    if(r.code===0) biliAcctLoad();
  }catch(e){ el('biliacct_msg').textContent='网络错误'; }
}
async function biliAcctPoll(){
  try{
    const r=await fetch(B+'/api/bili/account/qr/poll').then(x=>x.json());
    if(r.code!==0){ el('biliacct_msg').textContent=r.message||'失败'; return; }
    if(r.state==='done'){ el('biliacct_msg').textContent='登录成功：'+(r.uname||r.uid); el('biliacct_qrbox').style.display='none'; biliAcctLoad(); }
    else el('biliacct_msg').textContent='状态：'+r.state;
  }catch(e){ el('biliacct_msg').textContent='网络错误'; }
}
async function biliAcctBrowse(dry){
  el('biliacct_msg').textContent='正在刷推荐流…';
  try{
    const r=await fetch(B+'/api/bili/account/action',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'browse', dry:!!dry})}).then(x=>x.json());
    const q=r.result||{};
    el('biliacct_msg').textContent=q.error?('失败：'+q.error):('刷到《'+(q.title||'')+'》 点赞:'+(q.liked?'是':'否')+' 评论:'+(q.commented?'有':'无')+(dry?'（预览）':''));
    biliAcctLoad();
  }catch(e){ el('biliacct_msg').textContent='网络错误'; }
}
async function biliAcctDm(){
  el('biliacct_msg').textContent='发送中…';
  try{
    const r=await fetch(B+'/api/bili/account/action',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'dm', text:'在吗，测试一下私信'})}).then(x=>x.json());
    el('biliacct_msg').textContent=r.code===0?'已发送，去 B 站看看':(r.message||'失败');
    biliAcctLoad();
  }catch(e){ el('biliacct_msg').textContent='网络错误'; }
}
async function biliAcctLogs(){
  try{
    const r=await fetch(B+'/api/bili/account/logs').then(x=>x.json());
    el('biliacct_logs').innerHTML=(r.items||[]).map(function(x){
      const t=new Date(x.created_at*1000).toLocaleString();
      return '<div style="padding:3px 0">'+(x.ok?'✅':'❌')+' '+t+' · '+x.action+'：'+x.detail+'</div>';
    }).join('')||'还没有记录';
  }catch(e){}
}
async function biliAcctSave(){
  await fetch(B+'/api/bili/account/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    super_mid:el('biliacct_mid').value.trim(), super_uname:el('biliacct_uname').value.trim(),
    comment_max:el('biliacct_cmax').value, like_max:el('biliacct_lmax').value})});
  el('biliacct_msg').textContent='已保存'; biliAcctLoad();
}
function subsFor(key){
  const eff = (CURRENT_ROLE === 'viewer') ? 'super' : CURRENT_ROLE;
  const g = GROUP_DEFS.find(x=>x.key===key);
  if(!g || !g.subs) return [];
  let items = g.subs[eff] || g.subs.super || [];
  if(CURRENT_ROLE === 'viewer'){
    items = items.filter(function(pair){ return pair[0] !== 'logins'; });
  }
  return items;
}
function renderSubtabs(key){
  const items = subsFor(key);
  const bar = el('subtabs');
  bar.innerHTML = '';
  bar.style.display = items.length > 1 ? 'flex' : 'none';
  items.forEach(function(pair, idx){
    const d = document.createElement('div');
    d.className = 'tab' + (idx === 0 ? ' on' : '');
    d.textContent = pair[1];
    d.onclick = function(){
      bar.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on', x === d));
      showTab(pair[0]);
    };
    bar.appendChild(d);
  });
  if(items.length) showTab(items[0][0]);
}
function buildTabs(){
  const bar = el('tabs');
  bar.innerHTML = '';
  let first = null;
  const effRole = (CURRENT_ROLE === 'viewer') ? 'super' : CURRENT_ROLE;
  GROUP_DEFS.forEach(function(g){
    if(g.key === 'logout'){
      const d = document.createElement('div');
      d.className = 'tab'; d.textContent = '退出';
      d.onclick = function(){ fetch(B + '/api/logout',{method:'POST'}).then(function(){ location.reload(); }); };
      bar.appendChild(d);
      return;
    }
    if(g.roles.indexOf(effRole) === -1) return;
    const d = document.createElement('div');
    d.className = 'tab';
    if(g.key === 'bot') d.innerHTML = '机器人 <span id="updot" style="display:none;color:#f87171">●</span>';
    else d.textContent = g.label;
    d.onclick = function(){
      bar.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on', x === d));
      renderSubtabs(g.key);
    };
    bar.appendChild(d);
    if(!first) first = d;
  });
  if(first){ first.classList.add('on'); first.onclick(); }
}
function isDesktopNav(){ return window.matchMedia('(min-width: 900px)').matches; }
function buildSidebar(){
  const bar = el('tabs');
  bar.innerHTML = '';
  const effRole = (CURRENT_ROLE === 'viewer') ? 'super' : CURRENT_ROLE;
  let firstGroup = null;
  GROUP_DEFS.forEach(function(g){
    if(g.key === 'logout'){
      const d = document.createElement('div');
      d.className = 'tab'; d.textContent = '退出';
      d.onclick = function(){ fetch(B + '/api/logout',{method:'POST'}).then(function(){ location.reload(); }); };
      bar.appendChild(d);
      return;
    }
    if(g.roles.indexOf(effRole) === -1) return;
    const wrap = document.createElement('div');
    wrap.className = 'navgroup';
    const main = document.createElement('div');
    main.className = 'tab';
    if(g.key === 'bot') main.innerHTML = '机器人 <span id="updot" style="display:none;color:#f87171">●</span>';
    else main.textContent = g.label;
    const subs = document.createElement('div');
    subs.className = 'subs';
    const items = subsFor(g.key);
    items.forEach(function(pair){
      const d = document.createElement('div');
      d.className = 'tab';
      d.textContent = pair[1];
      d.onclick = function(ev){
        if(ev) ev.stopPropagation();
        subs.querySelectorAll('.tab').forEach(function(x){ x.classList.toggle('on', x === d); });
        showTab(pair[0]);
      };
      subs.appendChild(d);
    });
    if(items.length === 1){
      main.onclick = function(){
        bar.querySelectorAll('.navgroup').forEach(function(x){ x.classList.remove('open'); });
        showTab(items[0][0]);
      };
      wrap.appendChild(main);
      bar.appendChild(wrap);
      if(!firstGroup) firstGroup = wrap;
      return;
    }
    main.onclick = function(){
      const wasOpen = wrap.classList.contains('open');
      bar.querySelectorAll('.navgroup').forEach(function(x){ x.classList.remove('open'); });
      if(!wasOpen){ wrap.classList.add('open'); }
      const first = subs.querySelector('.tab');
      if(first && !wasOpen) first.click();
    };
    wrap.appendChild(main);
    wrap.appendChild(subs);
    bar.appendChild(wrap);
    if(!firstGroup) firstGroup = wrap;
  });
  if(firstGroup){
    firstGroup.classList.add('open');
    const f = firstGroup.querySelector('.subs .tab');
    if(f) f.click();
  }
}
(function(){
  const orig = window.fetch.bind(window);
  const cache = new Map();
  let pending = 0;
  let busyBtns = [];
  window.__dshBusy = function(){ return pending > 0; };
  const release = function(){
    busyBtns.forEach(function(b){ b.disabled = false; });
    busyBtns = [];
  };
  document.addEventListener('click', function(e){
    const b = e.target && e.target.closest ? e.target.closest('button') : null;
    if(!b || b.disabled) return;
    setTimeout(function(){
      if(pending > 0 && !b.disabled){
        b.disabled = true;
        busyBtns.push(b);
      }
    }, 0);
  }, true);
  window.fetch = function(input, init){
    const method = ((init && init.method) || 'GET').toUpperCase();
    const url = (typeof input === 'string') ? input : ((input && input.url) || '');
    const key = method + ' ' + url;
    if(method === 'GET' && url.indexOf('/api/') !== -1){
      const hit = cache.get(key);
      if(hit && Date.now() - hit.t < 8000){
        return Promise.resolve(hit.r.clone());
      }
    }
    if(method !== 'GET') cache.clear();
    pending++;
    const bar = document.getElementById('pbar');
    if(bar){ bar.style.opacity = '1'; bar.style.width = '35%'; }
    return orig.apply(null, arguments).then(function(resp){
      if(method === 'GET' && url.indexOf('/api/') !== -1){
        try{ cache.set(key, { r: resp.clone(), t: Date.now() }); }catch(e){}
      }
      return resp;
    }).finally(function(){
      pending = Math.max(0, pending - 1);
      if(pending === 0){
        release();
        if(bar){ bar.style.width = '100%'; setTimeout(function(){ bar.style.width = '0'; bar.style.opacity = '0'; }, 180); }
      }
    });
  };
})();
async function initNav(){
  try{
    const r = await fetch(B + '/api/me').then(r=>r.json());
    if(r.code !== 0){ location.reload(); return; }
    CURRENT_ROLE = r.role || 'user';
    if(CURRENT_ROLE === 'viewer'){
      document.body.classList.add('viewer');
      const bar = document.createElement('div');
      bar.style.cssText = 'text-align:center;color:#fbbf24;font-size:13px;padding:8px 12px;border-bottom:1px solid #2a2f3a;background:rgba(251,191,36,.08)';
      bar.textContent = '观察者模式：只能查看，所有操作按钮已禁用';
      document.body.insertBefore(bar, document.body.firstChild);
    }
    if(isDesktopNav()) buildSidebar(); else buildTabs();
    window.addEventListener('resize', function(){
      const desktop = isDesktopNav();
      if(desktop !== window.__navDesktop){
        window.__navDesktop = desktop;
        if(desktop) buildSidebar(); else buildTabs();
      }
    });
    window.__navDesktop = isDesktopNav();
    if(CURRENT_ROLE !== 'user'){
      refreshStatus();
      setInterval(refreshStatus, 15000);
    }
  }catch(e){ location.reload(); }
}
initNav();
setTimeout(checkForceUpdate, 800);
setInterval(checkForceUpdate, 60000);

let BOT_EXPECT_NICK = '';
async function loadBlacklist(){
  const r = await fetch(B + '/api/blacklist').then(r=>r.json());
  const box = el('blacklist');
  box.innerHTML = '';
  if(!r.list || !r.list.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent = '（空）';
    box.appendChild(h);
    return;
  }
  r.list.forEach(function(item){
    const qq = item.qq;
    const row = document.createElement('div'); row.className='item';
    const img = document.createElement('img');
    img.src = 'https://q1.qlogo.cn/g?b=qq&nk=' + qq + '&s=100';
    img.style.cssText = 'width:34px;height:34px;border-radius:50%;vertical-align:middle;margin-right:8px;background:#222;flex:none';
    const span = document.createElement('span');
    let label = qq;
    if(item.nick){ label += ' · ' + item.nick; }
    span.textContent = label;
    span.style.cssText = 'flex:1;word-break:break-all';
    const btn = document.createElement('button'); btn.textContent = '移出';
    btn.style.background = '#b91c1c';
    btn.onclick = function(){ delBlack(qq); };
    row.appendChild(img); row.appendChild(span); row.appendChild(btn);
    box.appendChild(row);
  });
}
async function addBlack(){
  const qq = el('blackqq').value.trim();
  if(!qq){ el('blackmsg').textContent='先填 QQ 号'; return; }
  const r = await fetch(B + '/api/blacklist/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq: qq})}).then(r=>r.json());
  el('blackmsg').textContent = r.code===0 ? '已加入黑名单' : (r.message||'添加失败');
  el('blackmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){ el('blackqq').value=''; loadBlacklist(); }
}
async function delBlack(qq){
  const r = await fetch(B + '/api/blacklist/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq: qq})}).then(r=>r.json());
  if(r.code===0) loadBlacklist();
}
async function loadBotProfile(refresh){
  const r = await fetch(B + '/api/bot-profile' + (refresh ? '?refresh=1' : '')).then(r=>r.json());
  if(r.code!==0) return null;
  el('botuin').textContent = r.uin || '-';
  el('botnicklabel').textContent = r.nick || '-';
  if(r.avatar){
    el('botavatar').src = r.avatar + '&t=' + Date.now();
  }
  el('botnick').placeholder = '新昵称（当前：' + (r.nick||'-') + '）';
  return r;
}
async function syncBotName(attempt){
  const r = await loadBotProfile(true);
  if(!r) return;
  if(BOT_EXPECT_NICK && r.nick !== BOT_EXPECT_NICK && attempt < 3){
    setTimeout(function(){ syncBotName(attempt + 1); }, 60000);
  } else if(BOT_EXPECT_NICK && r.nick === BOT_EXPECT_NICK){
    el('botmsg').textContent = '昵称已同步：' + r.nick;
    el('botmsg').style.color = '#4ade80';
  }
}
async function saveBotNick(){
  const nick = el('botnick').value.trim();
  if(!nick){ el('botmsg').textContent = '先填昵称'; return; }
  if(!confirm('提示：QQ 机制在修改昵称时可能在「个签历史」里留下一条记录，介意请直接用手机 QQ 修改。仍要通过后台修改吗？')) return;
  const r = await fetch(B + '/api/bot-profile/nick',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nickname: nick})}).then(r=>r.json());
  el('botmsg').textContent = r.code===0 ? '昵称已修改' : (r.message||'修改失败');
  el('botmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){
    el('botnick').value='';
    BOT_EXPECT_NICK = nick;
    el('botmsg').textContent = '已提交修改，1 分钟后自动同步昵称…';
    el('botmsg').style.color = '#4ade80';
    setTimeout(function(){ syncBotName(0); }, 60000);
  }
}
async function saveBotAvatar(){
  const url = el('botavatarurl').value.trim();
  if(!url){ el('botmsg').textContent = '先填图片地址'; return; }
  const r = await fetch(B + '/api/bot-profile/avatar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url: url})}).then(r=>r.json());
  el('botmsg').textContent = r.code===0 ? '头像已提交修改（QQ 生效可能有延迟）' : (r.message||'修改失败');
  el('botmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){ el('botavatarurl').value=''; loadBotProfile(); }
}
async function loadWake(){
  const r = await fetch(B + '/api/wake').then(r=>r.json());
  if(r.code!==0) return;
  el('wakebtn').textContent = r.enabled ? '强制唤醒：已开启' : '强制唤醒：已关闭';
  el('wakebtn').style.background = r.enabled ? '#16a34a' : '#4b5563';
  el('wakemin').value = r.min;
  el('wakemax').value = r.max;
  el('wakereset').value = r.reset_minutes;
  const box = el('wakelog'); box.innerHTML = '';
  if(!r.today || !r.today.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent='（今天还没有被吵醒过）';
    box.appendChild(h); return;
  }
  r.today.forEach(function(it){
    const row = document.createElement('div'); row.className='hint';
    row.textContent = '群 ' + it.group_id + ' · 被吵醒 ' + it.count + ' 次 · 最后 ' + (it.last_at||'');
    box.appendChild(row);
  });
}
async function toggleWake(){
  const cur = el('wakebtn').textContent.indexOf('已开启') !== -1;
  await fetch(B + '/api/wake/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})});
  loadWake();
}
async function saveWake(){
  const r = await fetch(B + '/api/wake/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    min: el('wakemin').value, max: el('wakemax').value, reset_minutes: el('wakereset').value
  })}).then(r=>r.json());
  el('wakemsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('wakemsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadWake();
}
async function loadRest(){
  let r;
  try{
    r = await fetch(B + '/api/rest').then(r=>r.json());
  }catch(e){
    r = {code:-1};
  }
  if(r.code!==0){
    el('restbtn').textContent = '休息模式：加载失败，点击重试';
    el('restbtn').style.background = '#7f1d1d';
    el('restnotifybtn').textContent = '休息通知：加载失败';
    el('reststatus').textContent = '接口请求失败，请刷新页面';
    return;
  }
  el('reststart').value = r.start || '22:00';
  el('restend').value = r.end || '08:00';
  const btn = el('restbtn');
  btn.textContent = r.enabled ? '休息模式：已开启' : '休息模式：已关闭';
  btn.style.background = r.enabled ? '#16a34a' : '#4b5563';
  const nb = el('restnotifybtn');
  nb.textContent = r.notify ? '休息通知：已开启' : '休息通知：已关闭';
  nb.style.background = r.notify ? '#16a34a' : '#4b5563';
  el('reststatus').textContent = r.enabled
    ? (r.in_rest ? '当前处于休息时间：只回复超管私聊和休息白名单' : '当前不在休息时间段，正常回复')
    : '未开启休息模式，全天正常回复';
  renderRestList('restglist', r.groups || [], 'group');
  renderRestNotify(r.notify_groups || []);
  renderRestList('restulist', r.users || [], 'user');
  const g = (r.groups||[]).length, u = (r.users||[]).length;
  loadWake();
  el('restwl').textContent = u === 0
    ? ('休息 QQ 白名单为空 → 休息时只回复超级管理员私聊（防封号推荐）')
    : ('群 ' + g + ' 个，QQ ' + u + ' 个；休息时只回复这些群/QQ 和超级管理员私聊');
}
function renderRestList(boxId, values, type){
  const box = el(boxId);
  box.innerHTML = '';
  if(!values.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent='（空）';
    box.appendChild(h);
    return;
  }
  values.forEach(function(v){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.textContent = v;
    const btn = document.createElement('button'); btn.textContent = '删除';
    btn.style.background = '#b91c1c';
    btn.onclick = function(){ delRestWL(type, v); };
    row.appendChild(span); row.appendChild(btn);
    box.appendChild(row);
  });
}
async function addRestWL(type){
  const input = type === 'group' ? el('restg') : el('restu');
  const value = input.value.trim();
  if(!value){ el('restmsg').textContent='先填数字'; return; }
  const r = await fetch(B + '/api/rest/wl',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type: type, action: 'add', value: value})}).then(r=>r.json());
  el('restmsg').textContent = r.code===0 ? '已添加' : (r.message||'添加失败');
  el('restmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){ input.value=''; loadRest(); }
}
async function delRestWL(type, value){
  const r = await fetch(B + '/api/rest/wl',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type: type, action: 'remove', value: value})}).then(r=>r.json());
  if(r.code===0) loadRest();
}
async function importRestWL(){
  const r = await fetch(B + '/api/rest/import',{method:'POST'}).then(r=>r.json());
  el('restmsg').textContent = r.code===0 ? '已导入现有群/QQ白名单' : (r.message||'导入失败');
  el('restmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadRest();
}
async function toggleRest(){
  const cur = el('restbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/rest/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})}).then(r=>r.json());
  if(r.code===0) loadRest(); else alert(r.message||'操作失败');
}
function renderRestNotify(values){
  const box = el('restnotifylist');
  box.innerHTML = '';
  if(!values.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent='（未设置通知群，不发送休息通知）';
    box.appendChild(h);
    return;
  }
  values.forEach(function(v){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.textContent = v;
    const btn = document.createElement('button'); btn.textContent = '删除';
    btn.style.background = '#b91c1c';
    btn.onclick = function(){ delRestNotifyGroup(v); };
    row.appendChild(span); row.appendChild(btn);
    box.appendChild(row);
  });
}
async function addRestNotifyGroup(){
  const value = el('restnotifyg').value.trim();
  if(!value){ el('restmsg').textContent='先填群号'; return; }
  const r = await fetch(B + '/api/rest/notify-groups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'add', value: value})}).then(r=>r.json());
  el('restmsg').textContent = r.code===0 ? '已添加通知群' : (r.message||'添加失败');
  el('restmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){ el('restnotifyg').value=''; loadRest(); }
}
async function delRestNotifyGroup(value){
  const r = await fetch(B + '/api/rest/notify-groups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'remove', value: value})}).then(r=>r.json());
  if(r.code===0) loadRest();
}
async function toggleRestNotify(){
  const cur = el('restnotifybtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/rest/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notify: !cur})}).then(r=>r.json());
  if(r.code===0) loadRest(); else alert(r.message||'操作失败');
}
async function saveRestTime(){
  const r = await fetch(B + '/api/rest/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start: el('reststart').value, end: el('restend').value})}).then(r=>r.json());
  el('restmsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('restmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadRest();
}
async function loadSettings(){
  const r = await fetch(B + '/api/update').then(r=>r.json());
  renderUpdate(r);
}
function renderUpdate(r){
  if(!r || r.code !== 0) return;
  let line = '当前版本：' + (r.current || '-');
  if(r.latest){
    line += ' ｜ 最新：' + r.latest + (r.date ? '（' + r.date + '）' : '');
  } else if(r.error){
    line += ' ｜ 检查失败：' + r.error;
  }
  el('verline').textContent = line;
  const nb = el('vernotes');
  nb.innerHTML = '';
  if(r.notes){
    const title = document.createElement('div');
    title.style.cssText = 'color:#fbbf24;margin:8px 0 4px;font-weight:600';
    title.textContent = '本版更新内容';
    nb.appendChild(title);
    String(r.notes).replace(new RegExp(String.fromCharCode(10), 'g'), '；').split('；').filter(function(x){return x.trim();}).forEach(function(line){
      const d = document.createElement('div');
      d.style.cssText = 'color:#c7ccd8;font-size:13px;line-height:1.7';
      d.textContent = '· ' + line.trim();
      nb.appendChild(d);
    });
  }
  const dot = el('updot');
  dot.style.display = r.has_update ? 'inline' : 'none';
  const btn = el('checkbtn');
  if(r.has_update){
    btn.textContent = r.force ? ('强制更新 → ' + (r.latest||'')) : ('立即更新 → ' + (r.latest||''));
    btn.style.background = '#16a34a';
    btn.onclick = applyUpdate;
    el('updatemsg').textContent = r.force ? '该版本要求强制更新' : '发现新版本，点击绿色按钮更新';
    el('updatemsg').style.color = r.force ? '#f87171' : '#fbbf24';
  } else {
    btn.textContent = '检查更新';
    btn.style.background = '#2563eb';
    btn.onclick = function(){ checkUpdate(true); };
  }
}
async function checkUpdate(force){
  const btn = el('checkbtn');
  btn.disabled = true;
  btn.textContent = '检查中…';
  el('updatemsg').textContent = '正在检查更新…';
  el('updatemsg').style.color = '#9aa4b8';
  try{
    const resp = await fetch(B + '/api/update' + (force ? '/check' : ''), {method:'POST'});
    if(!resp.ok) throw new Error('HTTP ' + resp.status);
    const r = await resp.json();
    if(r.code===0){
      renderUpdate(r);
      if(!r.has_update){
        el('updatemsg').textContent = '已是最新版本';
        el('updatemsg').style.color = '#4ade80';
      }
    } else {
      btn.textContent = '检查更新';
      el('updatemsg').textContent = r.message || '检查失败';
      el('updatemsg').style.color = '#f87171';
    }
  }catch(e){
    btn.textContent = '检查更新';
    el('updatemsg').textContent = '检查失败：' + (e && e.message ? e.message : '网络错误');
    el('updatemsg').style.color = '#f87171';
  }finally{
    btn.disabled = false;
    if(btn.textContent === '检查中…'){ btn.textContent = '检查更新'; }
  }
}
async function applyUpdate(){
  if(!confirm('确定更新到最新版本？更新后会自动重启，数据保留')) return;
  const msg = el('updatemsg');
  if(msg) msg.textContent = '下载并校验中…';
  const r = await fetch(B + '/api/update/apply',{method:'POST'}).then(r=>r.json());
  if(msg){
    msg.textContent = r.message || (r.code===0 ? '更新成功，重启中…' : '更新失败');
    msg.style.color = r.code===0 ? '#4ade80' : '#f87171';
  }else{
    alert(r.message || (r.code===0 ? '更新成功，重启中…' : '更新失败'));
  }
}
async function checkForceUpdate(){
  try{
    const r = await fetch(B + '/api/update/check',{method:'POST'}).then(r=>r.json());
    const bar = el('forcebar'), fl = el('forcefloat');
    if(r && r.force){
      el('forcebartext').textContent = '当前版本 ' + (r.current||'') + '，必须更新到 ' + (r.latest||'') + '（写入操作已暂停，聊天不受影响）';
      bar.style.display = 'block';
      fl.style.display = 'block';
      fl.textContent = '强制更新 → ' + (r.latest||'');
    }else{
      bar.style.display = 'none';
      fl.style.display = 'none';
    }
  }catch(e){}
}
let ECO={force:'0'};
function ecoPaint(){
  const on=ECO.force==='1';
  const b=el('eco_btn'); if(b){ b.textContent='省钱模式：'+(on?'已开启':'已关闭'); b.style.background=on?'#16a34a':'#374151'; b.style.color='#fff'; b.style.border='0'; }
}
async function loadEconomy(){
  try{
    const r=await fetch(B+'/api/economy/config').then(x=>x.json());
    if(r.code!==0){ el('ecomsg').textContent=r.message||'加载失败'; return; }
    ECO.force=r.force;
    el('eco_bal').textContent=(r.balance===null?'获取失败':Number(r.balance).toFixed(2));
    ecoPaint();
  }catch(e){ el('ecomsg').textContent='加载失败：'+e; }
}
async function economyToggle(){
  ECO.force=ECO.force==='1'?'0':'1'; ecoPaint();
  const r=await fetch(B+'/api/economy/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({force:ECO.force})}).then(x=>x.json());
  el('ecomsg').textContent=r.code===0?'':(r.message||'保存失败');
  el('ecomsg').style.color=r.code===0?'#4ade80':'#f87171';
}
async function loadHealth(){
  const out=el('opsout'), msg=el('opsmsg'); msg.textContent='检查中…';
  try{
    const r=await fetch(B+'/api/health').then(x=>x.json());
    if(r.code!==0){ msg.textContent=r.message||'失败'; return; }
    msg.textContent='';
    out.textContent=JSON.stringify({磁盘剩余GB:r.disk_free_gb,可用内存MB:r.mem_available_mb,QQ连接:r.napcat,问题:r.issues,数据库:r.db},null,2);
  }catch(e){ msg.textContent='失败：'+e; }
}
async function loadErrors(){
  const out=el('opsout'), msg=el('opsmsg'); msg.textContent='加载中…';
  try{
    const r=await fetch(B+'/api/errors').then(x=>x.json());
    if(r.code!==0){ msg.textContent=r.message||'失败'; return; }
    msg.textContent='';
    out.textContent=r.items.length?r.items.map(i=>`[${i.count}次] ${i.key}\n  首次 ${i.first} · 最近 ${i.last}`).join('\n\n'):'暂无错误';
  }catch(e){ msg.textContent='失败：'+e; }
}
function diagPackGuarded(){
  if(window.__noviceIssues === false){ alert('目前没有发现问题，不需要下载诊断包。'); return; }
  diagPack();
}
async function diagPack(){
  el('opsmsg').textContent='打包中…';
  try{
    const r=await fetch(B+'/api/diag/pack');
    if(!r.ok){ el('opsmsg').textContent='下载失败 HTTP '+r.status; return; }
    const blob=await r.blob(); const a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download='fishpond-diag.zip'; a.click();
    el('opsmsg').textContent='已下载';
  }catch(e){ el('opsmsg').textContent='失败：'+e; }
}
async function rollbackUpdate(){
  if(!confirm('确认回滚到上一版快照？会覆盖当前代码和数据库。')) return;
  el('opsmsg').textContent='回滚中…';
  try{
    const r=await fetch(B+'/api/rollback',{method:'POST'}).then(x=>x.json());
    el('opsmsg').textContent=r.code===0?(r.message||'已回滚'):(r.message||'失败');
  }catch(e){ el('opsmsg').textContent='失败：'+e; }
}
function superTab(name, node){
  document.querySelectorAll('.superpanel').forEach(function(x){ x.classList.add('hidden'); });
  const panel = el('super-' + name);
  if(panel) panel.classList.remove('hidden');
  if(name === 'friend') loadFriend();
  if(name === 'recall') loadRecall();
  const bar = el('supertabs');
  if(bar) bar.querySelectorAll('.tab').forEach(function(t){ t.classList.toggle('on', t === node); });
}
async function loadFriend(){
  const r = await fetch(B + '/api/friend').then(r=>r.json());
  if(r.code!==0){ el('friendlist').textContent = r.message || '无权限'; return; }
  el('fautobtn').textContent = r.auto ? '自动通过：已开启' : '自动通过：已关闭';
  el('fautobtn').style.background = r.auto ? '#16a34a' : '#4b5563';
  el('fnotifybtn').textContent = r.notify ? '超管提醒：已开启' : '超管提醒：已关闭';
  el('fnotifybtn').style.background = r.notify ? '#16a34a' : '#4b5563';
  el('flimit').value = r.limit;
  const box = el('friendlist'); box.innerHTML = '';
  const head = document.createElement('div'); head.className='hint';
  head.textContent = '今天：共 ' + r.today_total + ' 个申请，已通过 ' + r.today_accepted + ' 个';
  box.appendChild(head);
  if(!r.list.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent='（暂无好友申请记录）';
    box.appendChild(h); return;
  }
  const labels = {pending:'待处理', accepted:'已通过', rejected:'已拒绝', overlimit:'超上限', failed:'处理失败'};
  r.list.forEach(function(it){
    const row = document.createElement('div'); row.className='item'; row.style.flexWrap='wrap'; row.style.gap='6px';
    const cb = document.createElement('input'); cb.type='checkbox'; cb.className='slangcb'; cb.dataset.term=it.term; cb.style.marginTop='6px';
    cb.onchange=updateSlangSel;
    row.appendChild(cb);
    const span = document.createElement('span'); span.style.flex='1'; span.style.minWidth='200px';
    span.textContent = it.user_id + ' · ' + (labels[it.action]||it.action) + (it.comment ? (' · ' + it.comment) : '') + ' · ' + (it.created_at||'');
    row.appendChild(span);
    if(it.action === 'pending'){
      const ok = document.createElement('button'); ok.textContent='通过';
      ok.onclick = function(){ friendAct(it.flag, true); };
      row.appendChild(ok);
      const no = document.createElement('button'); no.className='danger'; no.textContent='拒绝';
      no.onclick = function(){ friendAct(it.flag, false); };
      row.appendChild(no);
    }
    box.appendChild(row);
  });
}
async function toggleFriendAuto(){
  const cur = el('fautobtn').textContent.indexOf('已开启') !== -1;
  await fetch(B + '/api/friend/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto: !cur})});
  loadFriend();
}
async function toggleFriendNotify(){
  const cur = el('fnotifybtn').textContent.indexOf('已开启') !== -1;
  await fetch(B + '/api/friend/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notify: !cur})});
  loadFriend();
}
async function saveFriendCfg(){
  await fetch(B + '/api/friend/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit: el('flimit').value})});
  loadFriend();
}
async function friendAct(flag, approve){
  const r = await fetch(B + '/api/friend/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({flag:flag, approve:approve})}).then(r=>r.json());
  if(r.code!==0) alert(r.message||'处理失败'); else loadFriend();
}
async function loadFriendBrief(){
  try{
    const r = await fetch(B + '/api/friend').then(r=>r.json());
    if(r.code!==0){ el('friendbrief').textContent = '无权限查看'; return; }
    el('friendbrief').textContent = '今天收到 ' + r.today_total + ' 个好友申请，已通过 ' + r.today_accepted + ' 个；自动通过：' + (r.auto ? '开启' : '关闭');
    const box = el('friendrecent'); box.innerHTML = '';
    const labels = {pending:'待处理', accepted:'已通过', rejected:'已拒绝', overlimit:'超上限', failed:'处理失败'};
    r.list.slice(0,5).forEach(function(it){
      const row = document.createElement('div'); row.className='hint';
      row.textContent = it.user_id + ' · ' + (labels[it.action]||it.action) + ' · ' + (it.created_at||'');
      box.appendChild(row);
    });
  }catch(e){}
}
async function loadSuper(){
  const r = await fetch(B + '/api/super?_=' + Date.now()).then(r=>r.json());
  if(r.code!==0) return;
  el('superqqs').value = (r.qqs || []).join(',');
  const sb = el('simpbtn');
  sb.textContent = r.simp ? '舔狗模式：已开启' : '舔狗模式：已关闭';
  sb.style.background = r.simp ? '#16a34a' : '#4b5563';
  const eb = el('exclbtn');
  eb.textContent = r.exclusive ? '专一模式：已开启' : '专一模式：已关闭';
  eb.style.background = r.exclusive ? '#16a34a' : '#4b5563';
  el('exwin').value = r.window_seconds || 60;
  el('roastwords').value = r.roast_keywords || '怼';
  el('roastlevel').value = r.roast_level == null ? 1 : r.roast_level;
  updateRoastLabel();
  setRoastModeUI(r.roast_mode || 'fast');
  el('balwords').value = r.balance_keywords || '';
  el('capwords').value = r.sticker_capture_keywords || '';
  fetch(B+'/api/stickers').then(x=>x.json()).then(sr=>{
    if(sr.code!==0) return;
    const ab=el('stkauto');
    if(ab){ ab.textContent='AI自动收录：'+(String(sr.auto_collect)==='1'?'已开启':'已关闭'); ab.style.background=String(sr.auto_collect)==='1'?'#16a34a':'#4b5563'; }
    if(el('stkautoday')) el('stkautoday').value=sr.auto_daily||3;
  }).catch(function(){});
  const cb = el('capbtn');
  if(cb){
    cb.textContent = r.sticker_capture ? '收录：已开启' : '收录：已关闭';
    cb.style.background = r.sticker_capture ? '#16a34a' : '#4b5563';
  }
  const rb = el('roastbtn');
  rb.textContent = r.roast ? '怼人模式：已开启' : '怼人模式：已关闭';
  rb.style.background = r.roast ? '#16a34a' : '#4b5563';
  el('superdesc').textContent = (r.qqs && r.qqs.length)
    ? ('当前超管：' + r.qqs.join('、'))
    : '还没填超管 QQ，下面两个模式不会生效';
  loadBotProfile();
  loadBlacklist();
}
function setRoastModeUI(mode){
  const fast = el('roastfast'), think = el('roastthink');
  fast.style.background = mode === 'think' ? '#4b5563' : '#2563eb';
  think.style.background = mode === 'think' ? '#7c3aed' : '#4b5563';
  fast.textContent = mode === 'think' ? '快速模式' : '快速模式 ✓';
  think.textContent = mode === 'think' ? '思考模式 ✓' : '思考模式';
}
async function setRoastMode(mode){
  setRoastModeUI(mode);
  await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({roast_mode: mode})});
}
function setRoastLevel(v){
  el('roastlevel').value = v;
  updateRoastLabel();
  saveRoastLevel();
}
function updateRoastLabel(){
  const v = parseInt(el('roastlevel').value || '1');
  el('roastlvlabel').textContent = ['可爱级', '正常级', '贴吧级'][v] || '正常级';
}
async function saveRoastLevel(){
  const lv = parseInt(el('roastlevel').value || '1');
  try{
    await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({roast_level: lv})});
  }catch(e){}
}
async function toggleStickerAuto(){
  const r=await fetch(B+'/api/stickers').then(x=>x.json());
  const on=String(r.auto_collect)==='1';
  await fetch(B+'/api/stickers/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_collect:!on})});
  loadSuper();
}
async function saveStickerAutoDaily(){
  const n=parseInt(el('stkautoday').value||'3');
  const r=await fetch(B+'/api/stickers/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_daily:n})}).then(x=>x.json());
  el('stkmsg').textContent=r.code===0?'已保存，每天最多 '+n+' 张':(r.message||'保存失败');
}
async function saveCaptureWords(){
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sticker_capture_keywords: el('capwords').value})}).then(r=>r.json());
  el('supermsg').textContent = r.code===0 ? '收录关键词已保存' : (r.message||'保存失败');
  el('supermsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadSuper();
}
async function toggleCapture(){
  const cur = el('capbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sticker_capture: !cur})}).then(r=>r.json());
  if(r.code!==0) alert(r.message||'操作失败'); else loadSuper();
}
async function saveBalanceWords(){
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({balance_keywords: el('balwords').value})}).then(r=>r.json());
  el('supermsg').textContent = r.code===0 ? '余额关键词已保存' : (r.message||'保存失败');
  el('supermsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadSuper();
}
async function toggleRoast(){
  const cur = el('roastbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({roast: !cur})}).then(r=>r.json());
  if(r.code===0) loadSuper(); else alert(r.message||'操作失败');
}
async function saveRoastWords(){
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({roast_keywords: el('roastwords').value})}).then(r=>r.json());
  el('supermsg').textContent = r.code===0 ? '触发词已保存' : (r.message||'保存失败');
  el('supermsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadSuper();
}
async function saveSuperWindow(){
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({window_seconds: parseInt(el('exwin').value||'60')})}).then(r=>r.json());
  el('supermsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('supermsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadSuper();
}
async function saveSuperQQ(){
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qqs: el('superqqs').value})}).then(r=>r.json());
  el('supermsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('supermsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadSuper();
}
async function toggleSimp(){
  const cur = el('simpbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({simp: !cur})}).then(r=>r.json());
  if(r.code===0) loadSuper(); else alert(r.message||'操作失败');
}
async function toggleExclusive(){
  const cur = el('exclbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/super/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({exclusive: !cur})}).then(r=>r.json());
  if(r.code===0) loadSuper(); else alert(r.message||'操作失败');
}

let PERSONA_NEW = false;
let PERSONA_LIST = [];
let IMG_ENHANCE = true;
const IMG_MODELS = {
  siliconflow: [
    {v:'Tongyi-MAI/Z-Image-Turbo', t:'Z-Image-Turbo · 约¥0.1/张 · 快、便宜，日常首选', size:'1024x1024', steps:8},
    {v:'Tongyi-MAI/Z-Image', t:'Z-Image · 约¥0.3/张 · 细节更好，速度中等', size:'1024x1024', steps:25},
    {v:'Qwen/Qwen-Image', t:'Qwen-Image · 约¥0.3/张 · 中文和图中文字最强', size:'1024x1024', steps:25},
    {v:'Kwai-Kolors/Kolors', t:'Kolors · 免费 · 人物/二次元均衡', size:'1024x1024', steps:20}
  ],
  zhipu: [
    {v:'glm-image', t:'GLM-Image · ¥0.1/次 · 海报/文字最强，默认 1280', size:'1280x1280', steps:0},
    {v:'cogview-4', t:'CogView-4 · ¥0.06/次 · 中文与汉字生成不错', size:'1024x1024', steps:0},
    {v:'cogview-4-250304', t:'CogView-4-250304 · ¥0.06/次 · 固定版本', size:'1024x1024', steps:0},
    {v:'cogview-3-flash', t:'CogView-3-Flash · 免费 · 快、质量一般', size:'1024x1024', steps:0}
  ]
};
let IMG_PROVIDER = 'siliconflow';
function imgFillModels(provider, keep){
  const sel = el('imgmodel'); if(!sel) return;
  const list = IMG_MODELS[provider] || IMG_MODELS.siliconflow;
  sel.innerHTML = '';
  list.forEach(m => { const o = document.createElement('option'); o.value = m.v; o.textContent = m.t; sel.appendChild(o); });
  if(keep && list.some(m => m.v === keep)) sel.value = keep;
}
function updateImageEffective(){
  const eff = el('imgeff'); if(!eff) return;
  const pv = (IMG_PROVIDER === 'zhipu') ? '智谱' : '硅基流动';
  const sel = el('imgmodel');
  const opt = sel && sel.options[sel.selectedIndex];
  const name = opt ? opt.value : '—';
  const size = el('imgsize') ? el('imgsize').value : '';
  const steps = (IMG_PROVIDER === 'zhipu') ? '无步数' : ('步数 ' + (el('imgsteps').value || '默认'));
  eff.textContent = '当前生效：' + pv + ' · ' + name + ' · ' + size + ' · ' + steps;
}
function paintImageProvider(){
  ['siliconflow','zhipu'].forEach(p => {
    const b = el('imgpv-' + p); if(!b) return;
    b.style.background = (p === IMG_PROVIDER) ? '#2563eb' : '#4b5563';
  });
  const isZ = IMG_PROVIDER === 'zhipu';
  const st = el('imgsteps');
  if(st){ st.disabled = isZ; st.placeholder = isZ ? '智谱不适用' : '步数'; }
  const note = el('imgpvnote');
  if(note) note.textContent = isZ
    ? '当前：智谱（步数、负面提示词不生效；glm-image 固定 hd）'
    : '当前：硅基流动';
  updateImageEffective();
}
async function switchImageProvider(p){
  const same = (IMG_PROVIDER === p);
  IMG_PROVIDER = p;
  imgFillModels(p);
  applyImageModelPreset();
  paintImageProvider();
  if(same) return;   // 已经是这家：只刷新界面，不重复提交
  const r = await fetch(B + '/api/image/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({provider:p, model: el('imgmodel').value, size: el('imgsize').value})}).then(r=>r.json());
  const m = el('imgsave1');
  if(m){ m.textContent = r.code===0 ? ('已切到' + (p==='zhipu'?'智谱':'硅基流动')) : (r.message||'切换失败');
         m.style.color = r.code===0 ? '#4ade80' : '#f87171'; }
}
function applyImageModelPreset(){
  const m = el('imgmodel').value || '';
  const list = IMG_MODELS[IMG_PROVIDER] || [];
  const def = list.find(x => x.v === m);
  if(!def) return;
  if(def.size) el('imgsize').value = def.size;
  el('imgsteps').value = def.steps ? def.steps : '';
  updateImageEffective();
}
function setImageEnhanceUI(v){
  IMG_ENHANCE = !!v;
  const b = el('imgenhbtn');
  if(b){
    b.textContent = IMG_ENHANCE ? '提示词优化：已开启' : '提示词优化：已关闭';
    b.style.background = IMG_ENHANCE ? '#16a34a' : '#4b5563';
  }
}
function toggleImageEnhance(){ setImageEnhanceUI(!IMG_ENHANCE); }
async function loadImageCfg(){
  const r = await fetch(B + '/api/image?_=' + Date.now()).then(r=>r.json());
  if(r.code!==0) return;
  el('imgbtn').textContent = r.enabled ? '生图：已开启' : '生图：已关闭';
  el('imgbtn').style.background = r.enabled ? '#16a34a' : '#4b5563';
  el('imgbase').value = r.base_url || '';
  el('imgzhipubase').value = r.zhipu_base || '';
  IMG_PROVIDER = r.provider || 'siliconflow';
  imgFillModels(IMG_PROVIDER, r.model || '');
  paintImageProvider();
  el('imgzhipukey').value = '';
  el('imgzhipukey').placeholder = r.zhipu_masked ? ('已保存：' + r.zhipu_masked + '（留空不修改）') : '智谱 Key';
  el('imgsize').value = r.size || '1024x1024';
  el('imgsteps').value = r.steps || 8;
  el('imgnegative').value = r.negative || '';
  el('imgselfdesc').value = r.self_desc || '';
  el('imgselfstyle').value = r.self_style || '';
  el('imgselfneg').value = r.self_negative || '';
  el('imgselfref').value = r.self_ref || '';
  el('imgselfeditmodel').value = r.self_edit_model || '';
  el('imgselfeditprompt').value = r.self_edit_prompt || '';
  setImageEnhanceUI(r.enhance);
  el('imglimit').value = r.daily_limit || 5;
  el('imgscope').value = r.scope || 'all';
  const sb = el('imgsuperbtn');
  sb.textContent = '超管不限制：' + (r.super_unlimited ? '已开启' : '已关闭');
  sb.style.background = r.super_unlimited ? '#16a34a' : '#4b5563';
  el('imgkey').value = '';
  el('imgkey').placeholder = r.masked ? ('已保存：' + r.masked + '（留空不修改）') : 'API Key';
}
async function toggleImage(){
  const cur = el('imgbtn').textContent.indexOf('已开启') !== -1;
  const next = !cur;
  await fetch(B + '/api/image/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: next})});
  el('imgbtn').textContent = '生图：' + (next ? '已开启' : '已关闭');
  el('imgbtn').style.background = next ? '#16a34a' : '#4b5563';
}
async function toggleImageSuperUnlimited(){
  const cur = el('imgsuperbtn').textContent.indexOf('已开启') !== -1;
  const next = !cur;
  await fetch(B + '/api/image/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({super_unlimited: next})});
  el('imgsuperbtn').textContent = '超管不限制：' + (next ? '已开启' : '已关闭');
  el('imgsuperbtn').style.background = next ? '#16a34a' : '#4b5563';
}
const IMG_PART_FIELDS = {
  iface: ['imgbase','imgkey','imgzhipubase','imgzhipukey','imgmodel','imgsize','imgsteps'],
  quota: ['imglimit','imgscope'],
  prompt: ['imgnegative'],
  self: ['imgselfref','imgselfeditmodel','imgselfstyle','imgselfdesc','imgselfneg','imgselfeditprompt']
};
const IMG_PART_KEYS = {
  iface: ['base_url','api_key','zhipu_base','zhipu_key','model','size','steps'],
  quota: ['daily_limit','scope'],
  prompt: ['negative'],
  self: ['self_ref','self_edit_model','self_style','self_desc','self_negative','self_edit_prompt']
};
function imagePartPayload(part){
  const ids = IMG_PART_FIELDS[part], keys = IMG_PART_KEYS[part], out = {};
  ids.forEach((id, i) => { out[keys[i]] = el(id).value; });
  if(part === 'iface'){ out.enhance = IMG_ENHANCE; out.provider = IMG_PROVIDER; }
  return out;
}
async function saveImagePart(part){
  const msgId = {iface:'imgsave1', quota:'imgsave2', prompt:'imgsave3', self:'imgsave4'}[part];
  const m = el(msgId);
  if(m){ m.textContent = '保存中…'; m.style.color = '#9aa4b8'; }
  let r = {code:-1, message:'保存失败'};
  try{
    r = await fetch(B + '/api/image/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(imagePartPayload(part))}).then(r=>r.json());
  }catch(e){ r = {code:-1, message:'网络错误'}; }
  if(m){
    m.textContent = r.code===0 ? '已保存' : (r.message || '保存失败');
    m.style.color = r.code===0 ? '#4ade80' : '#f87171';
  }
}
async function saveImage(){
  const body = Object.assign({}, imagePartPayload('iface'), imagePartPayload('quota'),
                             imagePartPayload('prompt'), imagePartPayload('self'));
  const r = await fetch(B + '/api/image/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
  const sm = el('imgsavemsg');
  sm.textContent = r.code===0 ? '已保存全部' : (r.message||'保存失败');
  sm.style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadImageCfg();
}
async function testImage(){
  el('imgmsg').textContent = '正在测试生图（可能要十几秒）…';
  el('imgmsg').style.color = '#9aa4b8';
  el('imgtestwrap').style.display = 'none';
  const prompt = (el('imgtestprompt').value || '').trim() || '一只猫在键盘上睡觉';
  const r = await fetch(B + '/api/image/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:prompt})}).then(r=>r.json());
  el('imgmsg').textContent = r.code===0 ? (r.message||'生成成功') : (r.message||'测试失败');
  el('imgmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0 && r.data_url){
    el('imgtestimg').src = r.data_url;
    el('imgtestwrap').style.display = 'block';
  }
}
async function loadSlang(){
  const r = await fetch(B + '/api/slang?_=' + Date.now()).then(r=>r.json());
  if(r.code!==0){ el('slanglist').textContent = r.message || '无权限'; return; }
  el('slangbtn').textContent = r.enabled ? '黑话模式：已开启' : '黑话模式：已关闭';
  el('slangbtn').style.background = r.enabled ? '#16a34a' : '#4b5563';
  el('slangevery').value = r.every;
  el('slangmodel').value = r.model || '';
  el('slangoptmodel').value = r.optimize_model || '';
  el('slangstop').value = r.stopwords || '';
  el('slangcount').textContent = '共 ' + r.list.length + ' 个词';
  const box = el('slanglist'); box.innerHTML = '';
  if(!r.list.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent='（空）还没有词，聊到会自动收录';
    box.appendChild(h); return;
  }
  r.list.forEach(function(it){
    const row = document.createElement('div'); row.className='item'; row.style.flexWrap='wrap'; row.style.gap='6px';
    const cb = document.createElement('input'); cb.type='checkbox'; cb.className='slangcb'; cb.dataset.term=it.term; cb.style.marginTop='6px';
    cb.onchange=updateSlangSel;
    row.appendChild(cb);
    const span = document.createElement('span'); span.style.flex='1'; span.style.minWidth='200px';
    span.textContent = it.term + '：' + (it.meaning||'') + (it.usage ? (' · ' + it.usage) : '') + ' · 命中 ' + (it.hits||0);
    row.appendChild(span);
    const ed = document.createElement('button'); ed.textContent='修改';
    ed.onclick = function(){ slangEdit(it); };
    row.appendChild(ed);
    const del = document.createElement('button'); del.className='danger'; del.textContent='删除';
    del.onclick = function(){ slangDel(it.term); };
    row.appendChild(del);
    box.appendChild(row);
  });
}
function updateSlangSel(){
  const boxes = Array.from(document.querySelectorAll('.slangcb'));
  const n = boxes.filter(function(b){return b.checked;}).length;
  const btn = el('slangallbtn');
  if(btn) btn.textContent = (n === boxes.length && boxes.length) ? '取消全选' : '全选';
}
function slangToggleAll(){
  const boxes = Array.from(document.querySelectorAll('.slangcb'));
  const all = boxes.length && boxes.every(function(b){return b.checked;});
  boxes.forEach(function(b){ b.checked = !all; });
  updateSlangSel();
}
async function slangDeleteSelected(){
  const terms = Array.from(document.querySelectorAll('.slangcb')).filter(function(b){return b.checked;}).map(function(b){return b.dataset.term;});
  if(!terms.length){ alert('没有选中词条'); return; }
  if(!confirm('确定删除选中的 ' + terms.length + ' 个词条？')) return;
  const r = await fetch(B + '/api/slang/delete_many',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({terms:terms})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'删除失败'); return; }
  loadSlang();
}
async function toggleSlang(){
  const cur = el('slangbtn').textContent.indexOf('已开启') !== -1;
  await fetch(B + '/api/slang/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})});
  loadSlang();
}
async function saveSlangCfg(){
  const r = await fetch(B + '/api/slang/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    every: el('slangevery').value, model: el('slangmodel').value,
    optimize_model: el('slangoptmodel').value, stopwords: el('slangstop').value
  })}).then(r=>r.json());
  el('slangmsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('slangmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadSlang();
}
async function slangSave(){
  const old = el('slangold').value;
  const payload = {term: el('slangterm').value, meaning: el('slangmean').value, usage: el('slangusage').value, old: old};
  const url = old ? '/api/slang/update' : '/api/slang/add';
  const r = await fetch(B + url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'保存失败'); return; }
  slangCancel();
  loadSlang();
}
function slangEdit(it){
  el('slangold').value = it.term;
  el('slangterm').value = it.term;
  el('slangmean').value = it.meaning || '';
  el('slangusage').value = it.usage || '';
  el('slangaddbtn').textContent = '保存修改';
  el('slangcancelbtn').style.display = '';
  el('slangterm').scrollIntoView({block:'center'});
}
function slangCancel(){
  el('slangold').value = '';
  el('slangterm').value = '';
  el('slangmean').value = '';
  el('slangusage').value = '';
  el('slangaddbtn').textContent = '添加';
  el('slangcancelbtn').style.display = 'none';
}
async function optimizeSlang(){
  if(!confirm('将把词库里的每条词都发给 AI 重新优化含义，耗时可能较长，继续吗？')) return;
  const btn = el('slangoptbtn');
  btn.disabled = true; btn.textContent = '优化中…';
  try{
    const r = await fetch(B + '/api/slang/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})}).then(r=>r.json());
    alert(r.code===0 ? ('已优化 ' + r.updated + ' 条，删除 ' + (r.deleted||0) + ' 条（共 ' + r.total + ' 条）') : (r.message||'优化失败'));
    loadSlang();
  }catch(e){ alert('优化失败'); }
  btn.disabled = false; btn.textContent = 'AI 优化词条';
}
async function slangDel(term){
  if(!confirm('删除「' + term + '」？')) return;
  await fetch(B + '/api/slang/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({term:term})});
  loadSlang();
}
async function loadMemory(){
  const q = el('memqq').value.trim(), kw = el('memkw').value.trim(), dt = el('memdate').value;
  const url = B + '/api/memory?qq=' + encodeURIComponent(q) + '&kw=' + encodeURIComponent(kw) + '&date=' + encodeURIComponent(dt);
  const r = await fetch(url).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'无权限'); return; }
  const c = r.config;
  el('membtn').textContent = c.enabled ? '记忆模式：已开启' : '记忆模式：已关闭';
  el('membtn').style.background = c.enabled ? '#16a34a' : '#4b5563';
  el('memsuperdays').value = c.super_days;
  el('memnormaldays').value = c.normal_days;
  el('memsuperlimit').value = c.super_limit;
  el('memnormallimit').value = c.normal_limit;
  el('memsuperinject').value = c.super_inject;
  el('memnormalinject').value = c.normal_inject;
  el('memextract').value = c.extract_every;
  if(c.review_model && !Array.from(el('memreviewmodel').options).some(function(o){return o.value===c.review_model;})){
    const op = document.createElement('option'); op.value = c.review_model; op.textContent = c.review_model; el('memreviewmodel').appendChild(op);
  }
  el('memreviewmodel').value = c.review_model || '';
  el('memcount').textContent = '共 ' + r.items.length + ' 条';
  const box = el('memlist'); box.innerHTML = '';
  if(!r.items.length){
    const parts = [];
    if(q) parts.push('QQ=' + q);
    if(kw) parts.push('关键词=' + kw);
    if(dt) parts.push('日期=' + dt);
    const h = document.createElement('div'); h.className='hint';
    h.textContent = parts.length > 1
      ? ('（没有匹配的记忆）当前条件：' + parts.join(' + ') + '，需同时满足，可减少条件再查')
      : ('（没有匹配的记忆' + (parts.length ? '：' + parts[0] : '') + '）');
    box.appendChild(h); return;
  }
  r.items.forEach(function(it){
    const row = document.createElement('div'); row.className='memitem';
    const main = document.createElement('div'); main.className='main';
    const title = document.createElement('div');
    const tag = document.createElement('span');
    tag.className = 'memtag' + (it.level === 'high' ? ' high' : '');
    tag.textContent = it.level === 'high' ? '超管' : '普通';
    title.appendChild(tag);
    if(it.permanent){
      const pt = document.createElement('span'); pt.className='memtag perm'; pt.textContent='永久';
      title.appendChild(pt);
    }
    const txt = document.createElement('span'); txt.textContent = it.content;
    title.appendChild(txt);
    main.appendChild(title);
    const meta = document.createElement('div'); meta.className='meta';
    meta.textContent = 'QQ ' + it.owner_qq + '　·　调用 ' + (it.use_count||0) + ' 次　·　' + (it.created_at||'');
    main.appendChild(meta);
    row.appendChild(main);

    const acts = document.createElement('div'); acts.className='acts';
    const ed = document.createElement('button'); ed.textContent='编辑';
    ed.onclick = function(){ memEdit(it); };
    acts.appendChild(ed);
    const del = document.createElement('button'); del.className='danger'; del.textContent='删除';
    del.onclick = function(){ memDelete(it.id); };
    acts.appendChild(del);
    const clr = document.createElement('button'); clr.textContent='清空该QQ'; clr.style.background='#7f1d1d';
    clr.onclick = function(){ if(confirm('清空 QQ ' + it.owner_qq + ' 的所有记忆？')) memClear(it.owner_qq); };
    acts.appendChild(clr);
    row.appendChild(acts);
    box.appendChild(row);
  });
}
let MEM_REVIEW_ITEMS = [];
let MEM_REVIEW_POLL = null;
async function aiReview(){
  if(!confirm('让 AI 批量判断哪些记忆值得保留？会消耗 token，数据多时需要一些时间。')) return;
  const btn = el('memreviewbtn');
  if(btn){ btn.disabled = true; }
  try{
    const r = await fetch(B + '/api/memory/ai_review').then(r=>r.json());
    if(r.code!==0){ alert(r.message||'审核失败'); return; }
    if(!r.total){ alert('还没有记忆'); return; }
    el('memprogoverlay').classList.remove('hidden');
    updateMemProg(0, r.total);
    pollMemReview();
  }catch(e){ alert('审核失败'); }
  finally{ if(btn){ btn.disabled = false; } }
}
function updateMemProg(done, total){
  const pct = total ? Math.min(100, Math.round(done * 100 / total)) : 0;
  el('memprogbar').style.width = pct + '%';
  el('memprogtxt').textContent = '已处理 ' + done + ' / ' + total + ' 条（' + pct + '%）';
}
async function pollMemReview(){
  if(MEM_REVIEW_POLL) clearTimeout(MEM_REVIEW_POLL);
  try{
    const r = await fetch(B + '/api/memory/ai_review/status?_=' + Date.now()).then(r=>r.json());
    if(r.code!==0){ el('memprogoverlay').classList.add('hidden'); alert(r.message||'审核失败'); return; }
    updateMemProg(r.done, r.total);
    if(r.status === 'running'){
      MEM_REVIEW_POLL = setTimeout(pollMemReview, 700);
      return;
    }
    el('memprogoverlay').classList.add('hidden');
    if(r.status === 'error'){ alert('审核失败：' + (r.error || '未知错误')); return; }
    if(!r.items || !r.items.length){ alert('AI 认为当前记忆都值得保留'); return; }
    showMemReview({items:r.items, ids:r.ids, total:r.total});
  }catch(e){
    el('memprogoverlay').classList.add('hidden');
    alert('审核失败');
  }
}
function showMemReview(r){
  MEM_REVIEW_ITEMS = r.items || [];
  el('memreviewtitle').textContent = 'AI 建议删除（共 ' + MEM_REVIEW_ITEMS.length + ' 条）';
  el('memreviewhint').textContent = '勾选 = 删除，取消勾选 = 保留；共审核 ' + r.total + ' 条。';
  const box = el('memreviewlist'); box.innerHTML = '';
  MEM_REVIEW_ITEMS.forEach(function(it, idx){
    const row = document.createElement('label');
    row.style.cssText = 'display:flex;gap:10px;align-items:flex-start;padding:8px 4px;border-bottom:1px solid #1c2029;cursor:pointer';
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = true; cb.dataset.idx = idx; cb.style.marginTop = '4px';
    cb.onchange = updateMemReviewCount;
    const txt = document.createElement('div');
    txt.style.cssText = 'flex:1;font-size:13px;line-height:1.6';
    txt.textContent = it.content;
    if(it.reason){
      const why = document.createElement('div');
      why.className = 'hint'; why.textContent = '理由：' + it.reason;
      txt.appendChild(why);
    }
    row.appendChild(cb); row.appendChild(txt); box.appendChild(row);
  });
  updateMemReviewCount();
  el('memreviewmodal').classList.remove('hidden');
}
function updateMemReviewCount(){
  const boxes = el('memreviewlist').querySelectorAll('input[type=checkbox]');
  let n = 0; boxes.forEach(function(b){ if(b.checked) n++; });
  el('memreviewcount').textContent = '已选 ' + n + ' / ' + boxes.length + ' 条';
  el('memreviewtoggle').textContent = (n === boxes.length && boxes.length) ? '取消全选' : '全选';
}
function memReviewToggleAll(){
  const boxes = el('memreviewlist').querySelectorAll('input[type=checkbox]');
  const all = Array.from(boxes).every(function(b){ return b.checked; });
  boxes.forEach(function(b){ b.checked = !all; });
  updateMemReviewCount();
}
function closeMemReview(){ el('memreviewmodal').classList.add('hidden'); }
async function memReviewDelete(){
  const boxes = Array.from(el('memreviewlist').querySelectorAll('input[type=checkbox]'));
  const ids = boxes.filter(function(b){ return b.checked; }).map(function(b){ return MEM_REVIEW_ITEMS[parseInt(b.dataset.idx)].id; });
  if(!ids.length){ alert('没有勾选任何条目'); return; }
  if(!confirm('确定删除选中的 ' + ids.length + ' 条记忆？')) return;
  const r = await fetch(B + '/api/memory/delete_many',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:ids})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'删除失败'); return; }
  closeMemReview(); loadMemory();
}
async function toggleMemory(){
  const cur = el('membtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/memory/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'操作失败'); return; }
  loadMemory();
}
async function loadReviewModels(){
  try{
    const p = await fetch(B + '/api/providers').then(r=>r.json());
    const active = (p.providers || []).find(function(x){ return x.active; }) || (p.providers||[])[0];
    if(!active){ alert('还没有保存的模型供应商'); return; }
    const r = await fetch(B + '/api/providers/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:active.name})}).then(r=>r.json());
    if(r.code!==0){ alert(r.message||'获取失败'); return; }
    const sel = el('memreviewmodel');
    const cur = sel.value;
    sel.innerHTML = '<option value="">当前默认模型</option>' +
      (r.models||[]).map(function(m){ return '<option value="' + m + '">' + m + '</option>'; }).join('');
    if(cur) sel.value = cur;
  }catch(e){ alert('获取失败'); }
}
async function saveMemoryConfig(){
  const body = {
    super_days: el('memsuperdays').value, normal_days: el('memnormaldays').value,
    super_limit: el('memsuperlimit').value, normal_limit: el('memnormallimit').value,
    super_inject: el('memsuperinject').value, normal_inject: el('memnormalinject').value,
    extract_every: el('memextract').value,
    review_model: el('memreviewmodel').value
  };
  const r = await fetch(B + '/api/memory/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
  el('memmsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('memmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadMemory();
}
async function memAdd(){
  const r = await fetch(B + '/api/memory/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    qq: el('memaddqq').value.trim(), content: el('memaddtext').value.trim(), level: el('memaddlevel').value
  })}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'添加失败'); return; }
  el('memaddtext').value=''; loadMemory();
}
async function memEdit(it){
  const v = prompt('修改记忆内容', it.content);
  if(!v) return;
  const r = await fetch(B + '/api/memory/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:it.id, content:v})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'修改失败'); return; }
  loadMemory();
}
async function memDelete(id){
  if(!confirm('删除这条记忆？')) return;
  const r = await fetch(B + '/api/memory/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'删除失败'); return; }
  loadMemory();
}
async function memClear(qq){
  const r = await fetch(B + '/api/memory/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq:qq})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'清空失败'); return; }
  loadMemory();
}
async function memReset(){
  el('memqq').value=''; el('memkw').value=''; el('memdate').value='';
  loadMemory();
}
async function loadPersona(){
  const r = await fetch(B + '/api/personas').then(r=>r.json());
  if(r.code!==0) return;
  PERSONA_LIST = r.personas || [];
  const sel = el('personasel');
  sel.innerHTML = '<option value="0">默认人格（config）</option>' + PERSONA_LIST.map(function(p){
    return '<option value="'+p.id+'">'+p.name+'</option>';
  }).join('');
  const active = r.active && r.active !== '0' ? r.active : '0';
  sel.value = active;
  PERSONA_NEW = false;
  el('personatext').value = r.current;
  el('personaname').value = '';
  el('personalength').textContent = '当前：' + (sel.options[sel.selectedIndex]||{}).text + ' · ' + r.current.length + ' 字';
  try{
    const g = await fetch(B + '/api/persona').then(r=>r.json());
    const gb = el('genderbtn');
    if(gb){
      gb.textContent = g.gender_aware ? '性别感知：已开启' : '性别感知：已关闭';
      gb.style.background = g.gender_aware ? '#16a34a' : '#4b5563';
    }
  }catch(e){}
}
function onPersonaSelect(){
  const id = el('personasel').value;
  PERSONA_NEW = false;
  if(id === '0'){
    fetch(B + '/api/personas').then(r=>r.json()).then(function(r){
      el('personatext').value = r.default;
      el('personaname').value = '';
      el('personalength').textContent = '默认人格 · ' + r.default.length + ' 字';
    });
    return;
  }
  const p = PERSONA_LIST.find(function(x){ return String(x.id) === id; });
  if(p){
    el('personatext').value = p.content;
    el('personaname').value = p.name;
    el('personalength').textContent = p.name + ' · ' + p.content.length + ' 字';
  }
}
function newPersona(){
  PERSONA_NEW = true;
  el('personaname').value = '';
  el('personatext').value = '';
  el('personalength').textContent = '新建人格（填写名称和内容后保存）';
  el('personaname').focus();
}
async function toggleGender(){
  const cur = el('genderbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/persona/gender',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})}).then(r=>r.json());
  if(r.code===0) loadPersona(); else alert(r.message||'操作失败');
}
async function savePersona(){
  const name = el('personaname').value.trim();
  const content = el('personatext').value.trim();
  const sel = el('personasel').value;
  const id = PERSONA_NEW ? null : (sel !== '0' ? sel : null);
  const r = await fetch(B + '/api/personas/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id: id, name: name, content: content})}).then(r=>r.json());
  el('personamsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('personamsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){ PERSONA_NEW=false; loadPersona(); }
}
async function activatePersona(){
  const id = el('personasel').value || '0';
  const r = await fetch(B + '/api/personas/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id: id})}).then(r=>r.json());
  if(r.code===0){ loadPersona(); } else alert(r.message||'切换失败');
}
async function deletePersona2(){
  const sel = el('personasel').value;
  if(sel === '0'){ alert('默认人格不能删除'); return; }
  if(!confirm('确定删除这个人格？')) return;
  const r = await fetch(B + '/api/personas/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id: sel})}).then(r=>r.json());
  if(r.code===0){ loadPersona(); } else alert(r.message||'删除失败');
}

async function loadVoice(){
  const r = await fetch(B + '/api/voice').then(r=>r.json());
  if(r.code !== 0) return;
  setTTSUI(!!r.tts_enabled);
  if(el('voiceffmpeg')){
    el('voiceffmpeg').textContent = r.ffmpeg_ok
      ? '音视频处理：ffmpeg 已就绪（会去掉开头提示音并转 mp3）'
      : '⚠ 未检测到 ffmpeg：已改用纯 Python 去提示音；想转 mp3 请执行 sudo apt-get install -y ffmpeg 后重启（有免密 sudo 时程序会自动尝试安装）';
    el('voiceffmpeg').style.color = r.ffmpeg_ok ? '#9aa4b8' : '#fbbf24';
  }
  setSuperTextUI(!!r.super_text);
  el('ttsmode').value = r.tts_mode || 'voice_in';
  el('voiceengine').value = r.engine || 'tts';
  el('voice_name').value = r.voice_name || 'tongtong';
  if(el('voiceengine')) el('voiceengine').value = r.engine || 'tts';
  updateVoiceFields();
  if(el('voicespeed')) el('voicespeed').value = r.voice_speed || '1.0';
  el('zvstyle').value = r.zvoice_style || '';
  if(el('breezekey')){
    el('breezekey').placeholder = r.breeze_key_masked ? ('已保存：' + r.breeze_key_masked + '（留空不修改）') : 'xi-api-key';
    el('breezevoice').value = r.breeze_voice || '';
    el('breezemodel').value = r.breeze_model || 'breeze-tts-2';
  }
  el('zvoice_key').value = '';
  el('zvoice_key').placeholder = r.zvoice_key_masked
    ? ('已保存：' + r.zvoice_key_masked + '（留空不修改）') : '留空则复用智谱 Key（生图那个）';
  setASRUI(!!r.asr_enabled);
  el('asrengine').value = r.asr_engine || 'api';
  el('asrlocal').value = r.asr_local_model || 'base';
  el('asrbase').value = r.asr_base || '';
  el('asrmodel').value = r.asr_model || '';
  el('asrkey').value = '';
  el('asrkeyinfo').textContent = r.asr_key_masked
    ? ('已保存：' + r.asr_key_masked + '（留空不修改）') : '留空则会复用智谱 Key（生图/语音合成那个）';
  toggleASRFields();
}
function setTTSUI(on){
  const b = el('ttsbtn');
  if(b){ b.textContent = on ? 'TTS：已开启（点击关闭）' : 'TTS：已关闭（点击开启）';
         b.style.background = on ? '#16a34a' : '#4b5563'; }
}
function setASRUI(on){
  const b = el('asrbtn');
  if(b){ b.textContent = on ? '语音识别：已开启（点击关闭）' : '语音识别：已关闭（点击开启）';
         b.style.background = on ? '#16a34a' : '#4b5563'; }
}
let SUPER_TEXT_ON = false;
function setSuperTextUI(v){
  SUPER_TEXT_ON = !!v;
  const b = el('suptextbtn');
  if(b){
    b.textContent = SUPER_TEXT_ON ? '超管文字也回语音：已开启' : '超管文字也回语音：已关闭';
    b.style.background = SUPER_TEXT_ON ? '#16a34a' : '#4b5563';
  }
}
async function toggleSuperText(){
  setSuperTextUI(!SUPER_TEXT_ON);
  try{
    const r = await fetch(B + '/api/voice/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({super_text: SUPER_TEXT_ON})}).then(r=>r.json());
    if(r.code !== 0){ alert(r.message || '保存失败'); }
  }catch(e){ alert('网络错误'); }
}
async function toggleTTS(){
  const cur = el('ttsbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/voice/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({tts_enabled: !cur})}).then(r=>r.json());
  if(r.code === 0) setTTSUI(!cur); else alert(r.message||'操作失败');
}
async function toggleASR(){
  const cur = el('asrbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/voice/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({asr_enabled: !cur})}).then(r=>r.json());
  if(r.code === 0) setASRUI(!cur); else alert(r.message||'操作失败');
}
function fillZhipuAsr(){
  el('asrengine').value = 'api';
  toggleASRFields();
  el('asrbase').value = 'https://open.bigmodel.cn/api/paas/v4';
  el('asrmodel').value = 'glm-asr-2512';
  el('asrkeyinfo').textContent = 'Key 留空即可：会自动复用智谱 Key（生图/语音合成那个）';
  el('asrmsgsave').textContent = '已填入，记得点「保存语音识别设置」';
  el('asrmsgsave').style.color = '#fbbf24';
}
function toggleASRFields(){
  const api = el('asrengine').value === 'api';
  el('asrapifields').style.display = api ? 'block' : 'none';
  el('asrlocal').style.display = api ? 'none' : 'inline-block';
}
let voicePreviewTimer = null;
async function testVoiceKey(){
  const m = el('voicemsg');
  m.innerHTML = '<span class="spin"></span>正在测试 Key…'; m.style.color = '#9aa4b8';
  try{
    const r = await fetch(B + '/api/voice/keytest',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key: el('zvoice_key').value.trim(), engine: el('voiceengine').value})}).then(r=>r.json());
    m.textContent = (r.code === 0 ? '✅ ' : '❌ ') + (r.message || '');
    m.style.color = r.code === 0 ? '#4ade80' : '#f87171';
  }catch(e){ m.textContent = '测试请求失败'; m.style.color = '#f87171'; }
}
async function voiceDiag(){
  const box = el('voicediag');
  box.style.display = 'block';
  box.innerHTML = '<div class="hint">正在生成诊断音频…</div>';
  try{
    const r = await fetch(B + '/api/voice/diag',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.json());
    if(r.code !== 0){ box.innerHTML = '<div class="hint" style="color:#f87171">' + (r.message||'失败') + '</div>'; return; }
    box.innerHTML =
      '<div class="hint">版本 ' + r.version + '｜ffmpeg ' + (r.ffmpeg_ok?'ok':'missing') + '｜引擎 ' + r.engine +
      '｜原始 ' + r.raw_bytes + 'B / 处理后 ' + r.proc_bytes + 'B</div>' +
      '<div class="hint" style="margin-top:6px">① 原始合成音频（未处理）</div>' +
      '<audio controls src="' + r.raw_url + '" style="width:100%"></audio>' +
      '<div class="hint" style="margin-top:6px">② 后处理音频（去提示音后）</div>' +
      '<audio controls src="' + r.proc_url + '" style="width:100%"></audio>';
  }catch(e){ box.innerHTML = '<div class="hint" style="color:#f87171">请求失败</div>'; }
}
async function previewVoice(){
  const btn = el('previewbtn');
  const msg = el('voicemsg');
  if(btn) btn.disabled = true;
  let sec = 0;
  const paint = function(){
    if(msg){ msg.innerHTML = '<span class="spin"></span>正在合成语音… ' + sec + 's'; msg.style.color = '#9aa4b8'; }
  };
  paint();
  clearInterval(voicePreviewTimer);
  voicePreviewTimer = setInterval(function(){ sec++; paint(); }, 1000);
  const ctrl = new AbortController();
  const to = setTimeout(function(){ ctrl.abort(); }, 90000);
  try{
    const r = await fetch(B + '/api/voice/preview',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({}), signal: ctrl.signal}).then(r=>r.json());
    clearTimeout(to); clearInterval(voicePreviewTimer); voicePreviewTimer = null;
    if(r.code === 0 && r.url){
      const box = el('voicepreview'); box.style.display = 'block';
      const pl = el('voiceplayer'); pl.src = r.url; pl.load();
      try { await pl.play(); } catch(e) {}
      const kb = Math.round((r.bytes||0)/1024);
      msg.textContent = '已生成（用时 ' + (r.seconds||sec) + 's｜' + kb + 'KB），点上面的播放条播放';
      msg.style.color = '#4ade80';
    } else {
      msg.textContent = r.message || '合成失败'; msg.style.color = '#f87171';
    }
  }catch(e){
    clearTimeout(to); clearInterval(voicePreviewTimer); voicePreviewTimer = null;
    msg.textContent = (e && e.name === 'AbortError') ? '合成超时（90 秒），稍后再试' : '网络错误';
    msg.style.color = '#f87171';
  }
  if(btn) btn.disabled = false;
}
function paintVoiceButtons(e){
  [['ve-tts','tts'],['ve-voice','voice'],['ve-breeze','breeze']].forEach(function(pair){
    const b = el(pair[0]); if(!b) return;
    const on = (pair[1] === e);
    b.style.background = on ? '#2563eb' : '#1f2430';
    b.style.color = on ? '#fff' : '#c9d1d9';
    b.style.border = '1px solid ' + (on ? '#2563eb' : '#2a2f3a');
  });
}
function setVoiceEngine(v){
  if(el('voiceengine')) el('voiceengine').value = v;
  paintVoiceButtons(v);
  updateVoiceFields();
  fetch(B + '/api/voice/config', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({engine:v})}).catch(function(){});
}
function updateVoiceFields(){
  const e = el('voiceengine') ? el('voiceengine').value : 'tts';
  const z = el('vf-zhipu'), b = el('vf-breeze'), vn = el('vf-voicename');
  if(z) z.style.display = (e === 'breeze') ? 'none' : 'grid';
  if(b) b.style.display = (e === 'breeze') ? 'grid' : 'none';
  if(vn) vn.style.display = (e === 'breeze') ? 'none' : 'block';
  paintVoiceButtons(e);
}
function voiceTTSFields(){
  return {
    tts_mode: el('ttsmode').value,
    engine: el('voiceengine').value,
    voice_name: el('voice_name').value,
    voice_speed: el('voicespeed') ? el('voicespeed').value : '1.0',
    zvoice_style: el('zvstyle').value.trim(),
    zvoice_key: el('zvoice_key').value.trim(),
    breeze_key: el('breezekey') ? el('breezekey').value.trim() : '',
    breeze_voice: el('breezevoice') ? el('breezevoice').value.trim() : '',
    breeze_model: el('breezemodel') ? el('breezemodel').value : 'breeze-tts-2' 
  };
}
function voiceASRFields(){
  return {
    asr_engine: el('asrengine').value, asr_local_model: el('asrlocal').value,
    asr_base: el('asrbase').value.trim(), asr_model: el('asrmodel').value.trim(),
    asr_key: el('asrkey').value.trim()
  };
}
async function saveVoiceTTS(){
  const m = el('ttssavemsg');
  m.textContent = '保存中…'; m.style.color = '#9aa4b8';
  try{
    const r = await fetch(B + '/api/voice/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(voiceTTSFields())}).then(r=>r.json());
    m.textContent = r.code===0 ? '语音设置已保存' : (r.message||'保存失败');
    m.style.color = r.code===0 ? '#4ade80' : '#f87171';
    if(r.code === 0 && r.voice_key_masked){
      el('zvoice_key').value = '';
      el('zvoice_key').placeholder = '已保存：' + r.voice_key_masked + '（留空不修改）';
    }
  }catch(e){ m.textContent = '网络错误'; m.style.color = '#f87171'; }
}
async function saveVoiceASR(){
  const m = el('asrmsgsave');
  m.textContent = '保存中…'; m.style.color = '#9aa4b8';
  try{
    const r = await fetch(B + '/api/voice/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(voiceASRFields())}).then(r=>r.json());
    m.textContent = r.code===0 ? '语音识别设置已保存' : (r.message||'保存失败');
    m.style.color = r.code===0 ? '#4ade80' : '#f87171';
    if(r.code===0) el('asrkey').value = '';
  }catch(e){ m.textContent = '网络错误'; m.style.color = '#f87171'; }
}

let GAME_SCRIPTS = [];
function gameEsc(v){
  return String(v == null ? '' : v).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function gameFindName(id){
  const hit = GAME_SCRIPTS.find(function(x){ return String(x.id) === String(id); });
  return hit ? hit.name : ('#' + id);
}
async function loadGame(){
  try{
    const r = await fetch(B + '/api/game/overview').then(r=>r.json());
    if(r.code !== 0){ el('gamestats').textContent = r.message || '加载失败'; return; }
    GAME_SCRIPTS = (r.local_scripts || []).map(function(x){ return {id:x.id, name:x.name, local:true}; });
    (r.remote_scripts || []).forEach(function(x){
      if(!GAME_SCRIPTS.some(function(y){ return String(y.id) === String(x.id); })){
        GAME_SCRIPTS.push({id:x.id, name:x.name, remote:true});
      }
    });
    const sel = el('gamescript');
    sel.innerHTML = '<option value="">（先不分配剧本）</option>' + GAME_SCRIPTS.map(function(x){
      return '<option value="' + gameEsc(x.id) + '">' + gameEsc(x.name) + (x.remote ? '（远程）' : '') + '</option>';
    }).join('');
    const rb = (r.rest_bypass !== false);
    if(el('gamerestbtn')){
      el('gamerestbtn').textContent = '休息时段放行剧本玩家：' + (rb ? '已开启' : '已关闭');
      el('gamerestbtn').style.background = rb ? '#16a34a' : '#4b5563';
      el('gamerestbtn').dataset.enabled = rb ? '1' : '0';
    }
    const st = r.stats || {};
    el('gamestats').textContent = '剧本 ' + (st.scripts || 0) + ' 个 · 玩家 ' + (st.players || 0) +
      ' 个 · 总局数 ' + (st.runs || 0) + ' · 对话 ' + (st.messages || 0) + ' 条';
    // 玩家列表
    const box = el('gameplayers');
    box.innerHTML = (r.players || []).length ? (r.players || []).map(function(p){
      const on = p.active;
      return '<div style="border-top:1px solid #22262f;padding:10px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
        '<b>' + gameEsc(p.qq) + '</b>' +
        '<span class="hint">' + (p.script_id ? gameEsc(p.script_name || gameFindName(p.script_id)) : '未分配剧本') + '</span>' +
        '<span class="hint">第 ' + (p.current_run || 0) + ' 次 · ' + (p.turns || 0) + ' 回合 · 共 ' + (p.runs || 0) + ' 局</span>' +
        '<span class="hint">' + gameEsc(p.updated_at || '') + '</span>' +
        '<button onclick="gameToggle(&apos;' + gameEsc(p.qq) + '&apos;,' + (on ? 'false' : 'true') + ')" style="background:' + (on ? '#16a34a' : '#4b5563') + '">' + (on ? '已开启' : '已关闭') + '</button>' +
        '<button onclick="gameRestart(&apos;' + gameEsc(p.qq) + '&apos;)">重开</button>' +
        '<button onclick="gameShowRuns(&apos;' + gameEsc(p.qq) + '&apos;)">历史局</button>' +
        '<button class="danger" onclick="gameDelete(&apos;' + gameEsc(p.qq) + '&apos;)">删除</button>' +
        '</div>';
    }).join('') : '<div class="hint">还没有玩家，先在上方添加 QQ。</div>';
  }catch(e){ el('gamestats').textContent = '加载失败：' + e; }
  loadGameCtx();
}
async function hostingNodes(){
  try{
    const d = await fetch(B + '/api/hosting/nodes').then(r=>r.json());
    const sel = el('htnode'); if(!sel) return;
    const cur = sel.value;
    sel.innerHTML = (d.items||[]).map(function(n){
      return '<option value="' + esc(n.key) + '">' + esc(n.label||n.key) + '</option>';
    }).join('') || '<option value="hk">香港节点</option>';
    if(cur) sel.value = cur;
  }catch(e){}
}
let HOSTING_ITEMS = {};
async function hostingDeploy(){
  const m = el('dsmsg');
  const ip = el('dsip').value.trim(), user = el('dsuser').value.trim(),
        pass = el('dspass').value, port = el('dsport').value.trim() || '22',
        label = el('dslabel').value.trim() || ip;
  if(!ip || !user || !pass){ m.textContent = '请填 IP、账号、密码'; m.style.color='#f87171'; return; }
  m.textContent = '正在部署…（2~5 分钟，请勿关闭页面）'; m.style.color = '#9aa4b8';
  try{
    const r = await fetch(B + '/api/hosting/deploy_server', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ip:ip, user:user, password:pass, port:port, label:label})}).then(r=>r.json());
    m.textContent = (r.code===0 ? '✅ ' : '❌ ') + (r.message || '');
    m.style.color = r.code===0 ? '#4ade80' : '#f87171';
    loadHosting();
  }catch(e){ m.textContent = '部署请求失败：' + e; m.style.color = '#f87171'; }
}
async function loadHosting(){
  await hostingNodes();
  const node = el('htnode') ? el('htnode').value : 'hk';
  try{
    const r = await fetch(B + '/api/hosting/list?node=' + encodeURIComponent(node)).then(r=>r.json());
    const box = el('htrows'); if(!box) return;
    if(r.code !== 0){ box.innerHTML = '<div class="hint">' + esc(r.message||'加载失败') + '</div>'; return; }
    const items = r.items || [];
    if(!items.length){ box.innerHTML = '<div class="hint">当前节点还没有租户。</div>'; return; }
    HOSTING_ITEMS = {}; items.forEach(function(m){ HOSTING_ITEMS[m.id] = m; });
    box.innerHTML = items.map(function(m){
      const online = m.live.online;
      const badge = online ? '<span class="ht-badge ok">在线</span>'
        : (m.live.need_login ? '<span class="ht-badge warn">待扫码</span>' : '<span class="ht-badge bad">离线</span>');
      const qq = m.live.uin || m.bound_qq || '未绑定';
      return '<div class="ht-tenant">' +
        '<div class="ht-head"><span class="ht-name">' + esc(m.account || 'admin') + '</span>' + badge +
        '<span class="ht-info" style="margin:0;margin-left:auto">' + esc(m.expires_at||'') + ' · 剩 ' + (m.days_left||0) + ' 天</span></div>' +
        '<div class="ht-grid">' +
        '<div><b>绑定 QQ</b><br>' + esc(qq) + '</div>' +
        '<div><b>账号</b><br>' + esc(m.account || 'admin') + '</div>' +
        '<div><b>密码</b><br>' + esc(m.admin_pass || '') + '</div>' +
        '</div>' +
        '<div class="ht-link"><b style="color:#8b93a5;font-weight:400">后台地址</b>' +
        '<a target="_blank" href="' + esc(m.link) + '">' + esc(m.link) + '</a>' +
        '<button onclick="hostingCopyCard(&apos;' + esc(m.id) + '&apos;)">一键复制</button>' +
        '<button onclick="hostingQR(&apos;' + esc(m.id) + '&apos;)">二维码</button></div>' +
        '<div class="ht-btns">' +
        '<button onclick="hostingAct(&apos;' + esc(m.id) + '&apos;,&apos;start&apos;)">启动</button>' +
        '<button onclick="hostingAct(&apos;' + esc(m.id) + '&apos;,&apos;stop&apos;)">停止</button>' +
        '<button onclick="hostingRenew(&apos;' + esc(m.id) + '&apos;)">续期</button>' +
        '<button onclick="hostingPasswd(&apos;' + esc(m.id) + '&apos;,&apos;reset&apos;)">重置密码</button>' +
        '<button onclick="hostingPasswd(&apos;' + esc(m.id) + '&apos;,&apos;edit&apos;)">修改密码</button>' +
        '<button class="danger" onclick="hostingAct(&apos;' + esc(m.id) + '&apos;,&apos;delete&apos;)">删除</button></div>' +
        '</div>';
    }).join('');
  }catch(e){ const b=el('htrows'); if(b) b.innerHTML='<div class="hint">加载失败</div>'; }
}
function hostingCopyCard(id){
  const m = HOSTING_ITEMS[id]; if(!m) return;
  const text = '后台地址：' + (m.link||'') + '\n账号：' + (m.account||'admin') + '\n密码：' + (m.admin_pass||'');
  navigator.clipboard.writeText(text);
  el('htmsg').textContent = '已复制：后台地址 / 账号 / 密码';
}
async function hostingCreate(){
  const m = el('htmsg'); m.textContent = '创建中…'; m.style.color = '#9aa4b8';
  const r = await fetch(B + '/api/hosting/create', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({days: el('htdays').value || 30, node: el('htnode').value,
      account: el('htacct').value.trim() || 'admin', password: el('htpass').value})}).then(r=>r.json());
  m.textContent = r.code===0 ? (r.message||'已创建') : (r.message||'失败');
  m.style.color = r.code===0 ? '#4ade80' : '#f87171';
  loadHosting();
}
async function hostingPasswd(id, mode){
  let pw = '';
  if(mode === 'edit'){ pw = prompt('输入新密码（至少 6 位）') || ''; if(!pw) return; }
  const r = await fetch(B + '/api/hosting/passwd', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id:id, password:pw, node: el('htnode').value})}).then(r=>r.json());
  el('htmsg').textContent = r.code===0 ? (r.message||'已修改') : (r.message||'失败');
  loadHosting();
}
async function hostingAct(id, act){
  if(act === 'delete' && !confirm('删除租户 ' + id + ' ？数据会一起清除')) return;
  const m = el('htmsg'); m.textContent = '处理中…';
  const r = await fetch(B + '/api/hosting/action', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id:id, action:act, node: el('htnode').value})}).then(r=>r.json());
  m.textContent = r.message || ''; m.style.color = r.code===0 ? '#4ade80' : '#f87171';
  loadHosting();
}
async function hostingRenew(id){
  const d = prompt('续期天数', '30'); if(!d) return;
  const r = await fetch(B + '/api/hosting/action', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id:id, action:'renew', days:d, node: el('htnode').value})}).then(r=>r.json());
  el('htmsg').textContent = r.message || ''; loadHosting();
}
async function hostingQR(id){
  const r = await fetch(B + '/api/hosting/qr', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id:id, node: el('htnode').value})}).then(r=>r.json());
  if(r.code !== 0){ alert(r.message || '二维码获取失败'); return; }
  if(r.qrcode){ const w = window.open(''); w.document.write('<img src="' + r.qrcode + '" style="width:320px"><p>' + (r.qrcodeurl||'') + '</p>'); }
  else alert(r.qrcodeurl || '没有二维码');
}
async function loadGameCtx(){
  try{
    const r = await fetch(B + '/api/game/contexts').then(r=>r.json());
    const box = el('gamectx'); if(!box) return;
    if(r.code !== 0){ box.innerHTML = '<div class="hint">加载失败</div>'; return; }
    const items = r.items || [];
    if(!items.length){ box.innerHTML = '<div class="hint">还没有玩家在群里接入。</div>'; return; }
    box.innerHTML = items.map(function(c){
      return '<div style="border-top:1px solid #22262f;padding:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
        '<b>' + gameEsc(c.qq) + '</b>' +
        '<span class="hint">群 ' + gameEsc(c.group_id) + '</span>' +
        '<span class="hint">' + gameEsc(c.script || '') + '</span>' +
        '<span class="hint" style="color:' + (c.active ? '#4ade80' : '#9aa4b8') + '">' + (c.active ? '接入中' : '已断开') + '</span>' +
        '<span class="hint">' + gameEsc(c.updated_at || '') + '</span>' +
        (c.active ? '<button class="danger" onclick="gameKickCtx(&apos;' + gameEsc(c.qq) + '&apos;,&apos;' + gameEsc(c.group_id) + '&apos;)">断开</button>' : '') +
        '</div>';
    }).join('');
  }catch(e){ const box = el('gamectx'); if(box) box.innerHTML = '<div class="hint">加载失败</div>'; }
}
async function gameToggleRestBypass(){
  const btn = el('gamerestbtn'); if(!btn) return;
  const next = btn.dataset.enabled !== '1';
  const r = await gamePost('/api/game/rest_bypass', {enabled: next});
  if(r.code === 0){ loadGame(); }
}
async function gameKickCtx(qq, gid){
  const r = await gamePost('/api/game/context/kick', {qq: qq, group_id: gid});
  if(r.code === 0) loadGameCtx();
}
async function gamePost(url, body){
  return fetch(B + url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).then(r=>r.json());
}
async function gameAddPlayer(){
  const qq = el('gameqq').value.trim(), sid = el('gamescript').value;
  if(!qq){ el('gamemsg').textContent = '先填 QQ 号'; el('gamemsg').style.color = '#f87171'; return; }
  const r = await gamePost('/api/game/player', {action:'add', qq:qq, script_id: sid || null});
  el('gamemsg').textContent = r.code === 0 ? '已添加并私聊提醒' : (r.message || '失败');
  el('gamemsg').style.color = r.code === 0 ? '#4ade80' : '#f87171';
  if(r.code === 0){ el('gameqq').value = ''; loadGame(); }
}
async function gameToggle(qq, active){
  const r = await gamePost('/api/game/player', {action:'toggle', qq:qq, active:active});
  if(r.code !== 0) alert(r.message || '失败'); else loadGame();
}
async function gameRestart(qq){
  if(!confirm('确定重开 ' + qq + ' 的剧本吗？会新建一局并私聊发送建档卡。')) return;
  const r = await gamePost('/api/game/player', {action:'restart', qq:qq});
  if(r.code !== 0) alert(r.message || '失败'); else loadGame();
}
async function gameDelete(qq){
  if(!confirm('彻底删除玩家 ' + qq + ' ？\n存档、对话记录、群内接入都会一起删除，无法恢复。')) return;
  const r = await gamePost('/api/game/player', {action:'delete', qq:qq, purge:true});
  if(r.code !== 0){ alert(r.message || '失败'); return; }
  const d = r.deleted || {};
  alert('已删除：存档 ' + (d.runs||0) + ' 局，对话 ' + (d.messages||0) + ' 条，群接入 ' + (d.contexts||0) + ' 条');
  el('gamerunbox').style.display = 'none';
  loadGame();
}
async function gameShowRuns(qq){
  const r = await fetch(B + '/api/game/runs?qq=' + encodeURIComponent(qq)).then(r=>r.json());
  el('gamerunbox').style.display = 'block';
  el('gamerunqq').textContent = qq;
  el('gamemsgs').innerHTML = '<div class="hint">点上面某一局查看对话</div>';
  if(r.code !== 0){ el('gameruns').textContent = r.message || '加载失败'; return; }
  el('gameruns').innerHTML = (r.runs || []).length ? r.runs.map(function(x){
    return '<div style="border-top:1px solid #22262f;padding:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
      '<b>第 ' + x.run_no + ' 次</b><span class="hint">' + gameEsc(x.status) + ' · ' + x.turn_count + ' 回合 · ' + gameEsc(x.created_at) + '</span>' +
      '<button onclick="gameSelectRun(&apos;' + gameEsc(qq) + '&apos;,' + x.id + ')">继续这一局</button>' +
      '<button onclick="gameShowMsgs(' + x.id + ')">对话</button></div>';
  }).join('') : '<div class="hint">还没有历史局。</div>';
}
async function gameSelectRun(qq, runId){
  const r = await gamePost('/api/game/run/select', {qq:qq, run_id:runId});
  if(r.code !== 0) alert(r.message || '失败'); else { alert('已切到这一局，玩家发任意消息即可继续。'); loadGame(); }
}
async function gameShowMsgs(runId){
  const r = await fetch(B + '/api/game/messages?run_id=' + runId).then(r=>r.json());
  const box = el('gamemsgs');
  if(r.code !== 0){ box.textContent = r.message || '加载失败'; return; }
  box.innerHTML = (r.messages || []).map(function(m){
    const who = m.role === 'user' ? '玩家' : 'AI';
    const color = m.role === 'user' ? '#93c5fd' : '#c9d1d9';
    return '<div style="margin:6px 0;color:' + color + '"><b>' + who + '：</b>' +
      gameEsc(m.content).split(String.fromCharCode(10)).join('<br>') + '</div>';
  }).join('') || '<div class="hint">这一局还没有对话</div>';
}
async function loadProviders(){
  const r = await fetch(B + '/api/providers').then(r=>r.json());
  if(r.code!==0) return;
  PV_PRESETS = r.presets || [];
  const sel = el('pvpreset');
  sel.innerHTML = '<option value="">-- 选择预设 --</option>' +
    PV_PRESETS.map(function(p){ return '<option value="' + p.name + '">' + p.name + '</option>'; }).join('');
  const active = (r.providers || []).find(function(p){ return p.active; });
  el('pvcurrent').textContent = active
    ? ('当前使用：' + active.name + ' · ' + active.model + '（' + active.base_url + '）')
    : '当前使用：默认 DeepSeek（来自状态页 Key 或 .env）';
  const box = el('pvlist');
  box.innerHTML = '';
  if(!r.providers.length){
    const h = document.createElement('div'); h.className='hint';
    h.textContent = '（空）还没有配置供应商，用上面的表单添加';
    box.appendChild(h);
    return;
  }
  r.providers.forEach(function(p){
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid #242833;border-radius:10px;padding:10px 12px;margin-bottom:10px';
    const head = document.createElement('div');
    head.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap';
    const title = document.createElement('span');
    title.innerHTML = '<b>' + p.name + '</b>' + (p.active ? ' <span class="badge">使用中</span>' : '');
    head.appendChild(title);
    const btns = document.createElement('span');
    btns.style.display='flex'; btns.style.gap='6px'; btns.style.flexWrap='wrap';
    const edit = document.createElement('button'); edit.textContent='编辑';
    edit.onclick = function(){ editProvider(p); };
    btns.appendChild(edit);
    const t = document.createElement('button'); t.textContent='测试';
    t.onclick = function(){ testProvider(p.name); };
    btns.appendChild(t);
    const ml = document.createElement('button'); ml.textContent='模型列表'; ml.style.background='#0e7490';
    ml.onclick = function(){ loadModelsForProvider(p.name); };
    btns.appendChild(ml);
    if(!p.active){
      const act = document.createElement('button'); act.textContent='启用';
      act.onclick = function(){ activateProvider(p.name); };
      btns.appendChild(act);
    }
    const d = document.createElement('button'); d.className='danger'; d.textContent='删除';
    d.onclick = function(){ deleteProvider(p.name); };
    btns.appendChild(d);
    head.appendChild(btns);
    card.appendChild(head);
    const meta = document.createElement('div');
    meta.className='hint'; meta.style.marginTop='6px';
    meta.textContent = '模型：' + p.model + '　|　地址：' + p.base_url + '　|　Key：' + p.masked;
    card.appendChild(meta);
    const bal = document.createElement('div');
    bal.className = 'hint';
    bal.style.marginTop = '4px';
    bal.style.color = '#fbbf24';
    bal.dataset.bal = p.name;
    bal.textContent = '余额：查询中…';
    card.appendChild(bal);
    box.appendChild(card);
  });
  loadBalances(false);
  if(active){ loadModelsForProviderSilent(active.name); }
}
async function loadModelsForProviderSilent(name){
  try{
    const r = await fetch(B + '/api/providers/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})}).then(r=>r.json());
    if(r.code===0 && r.models && r.models.length){ fillModelOptions(r.models); }
  }catch(e){}
}
async function loadBalances(force){
  const btn = el('pvbalbtn');
  if(btn){ btn.disabled = true; }
  if(force && el('pvbalmsg')) el('pvbalmsg').textContent = '查询中…';
  try{
    const r = await fetch(B + '/api/providers/balances' + (force ? '?force=1' : '')).then(r=>r.json());
    const map = (r && r.balances) || {};
    document.querySelectorAll('[data-bal]').forEach(function(node){
      const name = node.dataset.bal;
      const v = map[name];
      node.textContent = v ? ('余额：' + v) : '余额：不支持查询 / 获取失败';
      node.style.color = v ? '#fbbf24' : '#6b7280';
    });
    if(force && el('pvbalmsg')) el('pvbalmsg').textContent = '已刷新';
  }catch(e){
    if(el('pvbalmsg')) el('pvbalmsg').textContent = '查询失败';
  }finally{
    if(btn){ btn.disabled = false; }
  }
}
async function loadModelsForForm(){
  const base = el('pvbase').value.trim(), key = el('pvkey').value.trim();
  if(!base || !key){ alert('先填地址和 Key（编辑已保存的模型时，可用卡片上的「模型列表」）'); return; }
  const r = await fetch(B + '/api/providers/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_url:base, api_key:key})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'获取失败'); return; }
  fillModelOptions(r.models || []);
}
function fillModelOptions(models){
  const sel = el('pvmodelsel');
  if(!sel) return;
  sel.innerHTML = '<option value="">可用模型（下拉选择）</option>' +
    (models||[]).map(function(m){ return '<option value="' + m + '">' + m + '</option>'; }).join('');
  el('pvmsg').textContent = models.length ? ('已读取 ' + models.length + ' 个可用模型，可在下拉框选择') : '没有读取到模型';
  el('pvmsg').style.color = models.length ? '#4ade80' : '#f87171';
}
function pickPvModel(v){
  if(!v) return;
  el('pvmodel').value = v;
}
async function loadModelsForProvider(name){
  const r = await fetch(B + '/api/providers/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'获取失败'); return; }
  fillModelOptions(r.models || []);
}
function newProvider(){
  el('pvname').value = '';
  el('pvbase').value = '';
  el('pvmodel').value = '';
  el('pvkey').value = '';
  el('pvpreset').value = '';
  el('pvmsg').textContent = '';
  el('pvmodaltitle').textContent = '添加模型';
  el('pvmodelsel').innerHTML = '<option value="">可用模型（下拉选择）</option>';
  el('pvmodal').classList.remove('hidden');
}
function closeProviderModal(){
  el('pvmodal').classList.add('hidden');
}
function applyPreset(){
  const name = el('pvpreset').value;
  const p = PV_PRESETS.find(function(x){ return x.name === name; });
  if(!p) return;
  if(name !== 'custom'){ el('pvname').value = name; }
  el('pvbase').value = p.base_url;
  el('pvmodel').value = p.model;
  el('pvmodaltitle').textContent = '修改模型';
  el('pvmodal').classList.remove('hidden');
}
async function autoDetectProvider(){
  const key = el('pvkey').value.trim();
  if(!key){ el('pvmsg').textContent='先粘贴 API Key'; el('pvmsg').style.color='#f87171'; return; }
  el('pvmsg').textContent = '正在探测…'; el('pvmsg').style.color='#9aa4b8';
  const r = await fetch(B + '/api/providers/autodetect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:key})}).then(r=>r.json());
  if(r.matches && r.matches.length){
    const m = r.matches[0];
    el('pvname').value = m.name;
    el('pvbase').value = m.base_url;
    el('pvmodel').value = m.model;
    el('pvmsg').textContent = r.message;
    el('pvmsg').style.color = '#4ade80';
  } else {
    el('pvmsg').textContent = r.message || '没有匹配到';
    el('pvmsg').style.color = '#f87171';
  }
}
async function saveProvider(){
  const r = await fetch(B + '/api/providers/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    name: el('pvname').value.trim(), base_url: el('pvbase').value.trim(),
    model: el('pvmodel').value.trim(), api_key: el('pvkey').value.trim()
  })}).then(r=>r.json());
  el('pvmsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('pvmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){ el('pvkey').value=''; closeProviderModal(); loadProviders(); }
}
function editProvider(p){
  el('pvname').value = p.name;
  el('pvbase').value = p.base_url;
  el('pvmodel').value = p.model;
  el('pvmodaltitle').textContent = '修改模型';
  el('pvmodal').classList.remove('hidden');
  el('pvkey').value = '';
  el('pvkey').placeholder = '留空 = 不修改 Key';
  el('pvmsg').textContent = '正在编辑 ' + p.name + '，改完点保存';
  el('pvmsg').style.color = '#9aa4b8';
}
async function activateProvider(name){
  const r = await fetch(B + '/api/providers/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})}).then(r=>r.json());
  if(r.code===0) loadProviders(); else alert(r.message||'操作失败');
}
async function testProvider(name){
  const r = await fetch(B + '/api/providers/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})}).then(r=>r.json());
  el('pvmsg').textContent = r.message || (r.code===0?'Key 有效':'Key 无效');
  el('pvmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
}
async function deleteProvider(name){
  const r = await fetch(B + '/api/providers/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})}).then(r=>r.json());
  if(r.code===0) loadProviders(); else alert(r.message||'删除失败');
}

async function refreshStatus(){
  try{
    const r = await fetch(B + '/api/status').then(r=>r.json());
    if(r.code!==0) return;
    const qq = r.qq||{};
    const bar = el('offlinebar');
    if(bar){
      const mins = r.offline_minutes || 0;
      const need = r.need_login || (r.qq && r.qq.online === false) || (!r.bridge_connected && mins >= 2);
      bar.style.display = need ? 'block' : 'none';
      const bt = el('offlinebartext');
      if(bt) bt.textContent = '机器人 QQ 已离线 ' + mins + ' 分钟，可能被踢下线 → 打开「状态」页点「申请扫码二维码」重新登录';
    }
    el('stat-card').innerHTML =
      row('桥接连接', r.bridge_connected?'<span class="ok">在线</span>':'<span class="bad">离线</span>')+
      row('QQ 登录', qq.online?'<span class="ok">在线</span>':'<span class="bad">下线/未知</span>')+
      row('QQ 号', (qq.uin||r.self_id||'-'))+
      row('昵称', esc(qq.nick||'-'))+
      row('模型', esc(r.model))+
      row('运行时长', fmtUptime(r.uptime))+
      row('收 / 发消息', r.messages+' / '+r.replies)+
      row('最近消息', r.last_message? (r.last_message.time+' '+esc(r.last_message.session)+' '+esc(r.last_message.user)+': '+esc(r.last_message.text)) : '-');
    const l = await fetch(B + '/api/logs').then(r=>r.json());
    if(l.code===0) el('logbox').textContent = (l.logs||[]).slice(-25).join('\n');
  }catch(e){}
}
function row(k,v){return '<div class="row"><span class="k">'+k+'</span><span>'+v+'</span></div>'}

let qrTimer = null, qrLeft = 0;
function qrTick(){
  if(qrLeft > 0){
    el('qrcountdown').textContent = '二维码剩余 ' + qrLeft + ' 秒，请尽快用手机 QQ 扫描';
    qrLeft--;
  } else {
    el('qrcountdown').textContent = '二维码已过期，请点「刷新二维码」';
    clearInterval(qrTimer);
    if(el('qrautorefresh').checked){
      setTimeout(function(){ getQR(false); }, 400);
    }
  }
}
async function restartNapcat(){
  if(!confirm('重启 QQ 连接会让机器人短暂离线（约 20~30 秒），确定吗？')) return;
  el('qrmsg').style.color = '#9aa4b8';
  el('qrmsg').textContent = '正在重启 NapCat…';
  const r = await fetch(B + '/api/napcat/restart',{method:'POST'}).then(r=>r.json());
  el('qrmsg').textContent = r.message || (r.code===0 ? '已重启' : '重启失败');
  el('qrmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){
    let left = 25;
    clearInterval(qrTimer);
    qrTimer = setInterval(function(){
      el('qrcountdown').textContent = '等待 NapCat 启动… ' + left + ' 秒';
      if(left-- <= 0){
        clearInterval(qrTimer);
        el('qrcountdown').textContent = '';
        getQR(true);
      }
    }, 1000);
  }
}
async function getQR(manual){
  clearInterval(qrTimer);
  el('qrbtn').disabled = true;
  el('qrmsg').textContent = '请求中…';
  el('qrimg').innerHTML = ''; el('qrinfo').textContent=''; el('qrcountdown').textContent='';
  try{
    const r = await fetch(B + '/api/qr',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({force: !!manual})}).then(r=>r.json());
    if(r.code===0 && r.qrcode){
      el('qrimg').innerHTML = '<img class="qr" src="'+r.qrcode+'">';
      el('qrinfo').textContent = '请用手机 QQ「扫一扫」摄像头扫描（不要用相册/长按识别）';
      const age = r.age || 0;
      el('qrmsg').textContent = r.cached
        ? ('这是 ' + age + ' 秒前生成的码，仍有效（约 100 秒）')
        : '新二维码已生成，约 100 秒内有效';
      qrLeft = Math.max(20, 100 - age);
      qrTick();
      qrTimer = setInterval(qrTick, 1000);
    } else if(r.need_restart){
      el('qrmsg').textContent = r.message || 'NapCat 状态卡死，需要重启';
      el('qrmsg').style.color = '#f87171';
    } else {
      el('qrmsg').textContent = r.message || '申请失败';
      el('qrmsg').style.color = '#f87171';
    }
  }catch(e){ el('qrmsg').textContent = '网络错误'; }
  setTimeout(()=>{ el('qrbtn').disabled=false; }, 61000);
}

function renderList(containerId, values, onDel, emptyText){
  const box = el(containerId);
  box.innerHTML = '';
  if(!values.length){
    const hint = document.createElement('div');
    hint.className = 'hint';
    hint.textContent = emptyText || '（空）';
    box.appendChild(hint);
    return;
  }
  values.forEach(function(v){
    const row = document.createElement('div'); row.className = 'item';
    const span = document.createElement('span'); span.textContent = v;
    const btn = document.createElement('button'); btn.className = 'danger'; btn.textContent = '删除';
    btn.onclick = function(){ onDel(v); };
    row.appendChild(span); row.appendChild(btn);
    box.appendChild(row);
  });
}

async function loadWL(){
  const r = await fetch(B + '/api/whitelist').then(r=>r.json());
  if(r.code!==0){ alert(r.message||'无权限'); return; }
  renderWlList('glist', r.groups||[], 'group', r);
  renderWlList('ulist', r.users||[], 'user', r);
  const qg = r.role==='super' ? '不限' : (r.quota_groups==null ? '不限' : (r.used_groups+' / '+r.quota_groups));
  const qu = r.role==='super' ? '不限' : (r.quota_users==null ? '不限' : (r.used_users+' / '+r.quota_users));
  el('wlquota').textContent = '你的配额：群 ' + qg + ' ｜ QQ ' + qu + (r.role==='user' ? '（只能看到和删除自己添加的）' : '');
}
function renderWlList(id, items, type, r){
  const box = el(id);
  box.innerHTML = '';
  if(!items.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent = (type==='group' ? '（空）允许所有群' : '（空）允许所有人');
    box.appendChild(h);
    return;
  }
  items.forEach(function(it){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span');
    span.textContent = it.id + (it.owner ? (' · 由 ' + it.owner + ' 添加') : '');
    span.style.flex = '1';
    row.appendChild(span);
    const can = (r.role !== 'user') || it.mine;
    if(can){
      const ed = document.createElement('button'); ed.textContent = '修改';
      ed.style.background = '#4b5563';
      ed.onclick = function(){ editWL(type, it.id); };
      row.appendChild(ed);
      const del = document.createElement('button'); del.textContent = '删除';
      del.style.background = '#b91c1c';
      del.onclick = function(){ delWL(type, it.id); };
      row.appendChild(del);
    }
    box.appendChild(row);
  });
}
async function addWL(type){
  const input = type==='group' ? el('ginput') : el('uinput');
  const v = input.value.trim(); if(!v) return;
  const r = await fetch(B + '/api/whitelist/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:type, value:v})}).then(r=>r.json());
  if(r.code===0){ input.value=''; loadWL(); } else { alert(r.message||'添加失败'); }
}
async function delWL(type, value){
  const r = await fetch(B + '/api/whitelist/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:type, value:value})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'删除失败'); return; }
  loadWL();
}
async function editWL(type, old){
  const nv = prompt('修改为新的' + (type==='group' ? '群号' : 'QQ号'), old);
  if(!nv || nv.trim() === old) return;
  const r = await fetch(B + '/api/whitelist/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:type, old:old, new:nv.trim()})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'修改失败'); return; }
  loadWL();
}

async function loadAccounts(){
  const r = await fetch(B + '/api/accounts').then(r=>r.json());
  if(r.code!==0){ el('acclist').textContent = r.message || '无权限'; return; }
  const isSuper = r.my_role === 'super';
  el('acchint').textContent = isSuper ? '你可以创建超级管理员/管理员/用户，并设置配额' : '你可以创建用户，并设置其配额';
  let opts = '<option value="user">用户</option>';
  if(isSuper){
    opts += '<option value="admin">管理员</option><option value="super">超级管理员</option>';
    if(r.viewer_enabled) opts += '<option value="viewer">观察者</option>';
  }
  el('accrole').innerHTML = opts;
  const box = el('acclist'); box.innerHTML = '';
  const labels = {super:'超级管理员', admin:'管理员', user:'用户', viewer:'观察者'};
  if(!r.accounts.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent='（暂无账号）';
    box.appendChild(h);
    return;
  }
  r.accounts.forEach(function(a){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.style.flex='1';
    const qg = (a.quota_groups == null) ? '不限' : a.quota_groups;
    const qu = (a.quota_users == null) ? '不限' : a.quota_users;
    span.textContent = a.username + ' · ' + (labels[a.role]||a.role) + ' · 配额 群' + qg + '/QQ' + qu
      + (a.last_login_at ? (' · 最近登录 ' + a.last_login_at) : '') + (a.disabled ? ' · 已禁用' : '');
    row.appendChild(span);
    const mk = function(label, bg, fn){ const b=document.createElement('button'); b.textContent=label; b.style.background=bg; b.onclick=fn; row.appendChild(b); };
    mk('改配额', '#4b5563', function(){ editAccount(a); });
    mk('重置密码', '#4b5563', function(){ resetAccountPassword(a.id); });
    mk(a.disabled ? '启用' : '禁用', a.disabled ? '#16a34a' : '#b45309', function(){ toggleAccount(a.id, !a.disabled); });
    mk('删除', '#b91c1c', function(){ deleteAccount(a); });
    box.appendChild(row);
  });
}
async function createAccount(){
  const r = await fetch(B + '/api/accounts/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    username: el('accname').value.trim(),
    password: el('accpass').value,
    role: el('accrole').value,
    quota_groups: el('accqg').value,
    quota_users: el('accqu').value
  })}).then(r=>r.json());
  el('accmsg').textContent = r.code===0 ? '创建成功' : (r.message||'创建失败');
  el('accmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0){ el('accname').value=''; el('accpass').value=''; loadAccounts(); }
}
async function editAccount(a){
  const qg = prompt('最多可添加群数（留空=不限）', a.quota_groups == null ? '' : a.quota_groups);
  if(qg === null) return;
  const qu = prompt('最多可添加 QQ 数（留空=不限）', a.quota_users == null ? '' : a.quota_users);
  if(qu === null) return;
  const r = await fetch(B + '/api/accounts/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:a.id, quota_groups:qg.trim(), quota_users:qu.trim()})}).then(r=>r.json());
  if(r.code!==0) alert(r.message||'保存失败');
  loadAccounts();
}
async function resetAccountPassword(id){
  const pw = prompt('输入新密码（至少6位）');
  if(!pw) return;
  const r = await fetch(B + '/api/accounts/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id, password:pw})}).then(r=>r.json());
  if(r.code!==0) alert(r.message||'重置失败'); else alert('密码已重置');
}
async function toggleAccount(id, disabled){
  const r = await fetch(B + '/api/accounts/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id, disabled:disabled})}).then(r=>r.json());
  if(r.code!==0) alert(r.message||'操作失败'); else loadAccounts();
}
async function deleteAccount(a){
  if(!confirm('确定删除账号 ' + a.username + '？')) return;
  const r = await fetch(B + '/api/accounts/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:a.id})}).then(r=>r.json());
  if(r.code!==0) alert(r.message||'删除失败'); else loadAccounts();
}
async function loadLoginLogs(){
  const r = await fetch(B + '/api/login-logs').then(r=>r.json());
  const box = el('loginloglist'); box.innerHTML = '';
  if(r.code!==0){ box.textContent = r.message || '无权限'; return; }
  if(!r.logs.length){
    const h = document.createElement('div'); h.className='hint'; h.textContent='（暂无日志）';
    box.appendChild(h); return;
  }
  r.logs.forEach(function(l){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.style.flex='1';
    span.textContent = l.created_at + ' · ' + l.username + '(' + (l.role||'-') + ') · ' + (l.success ? '成功' : '失败')
      + ' · ' + (l.ip||'-') + (l.location ? (' · ' + l.location) : '') + (l.reason ? (' · ' + l.reason) : '');
    row.appendChild(span);
    box.appendChild(row);
  });
}

async function loadKW(){
  const r = await fetch(B + '/api/keywords').then(r=>r.json());
  if(r.code!==0) return;
  renderList('kwlist', r.keywords, delKW, '（空）暂无触发词');
}
async function addKW(){
  const v = el('kwinput').value.trim(); if(!v) return;
  const r = await fetch(B + '/api/keywords/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({word:v})}).then(r=>r.json());
  if(r.code===0){ el('kwinput').value=''; loadKW(); } else { alert(r.message||'添加失败'); }
}
async function delKW(w){
  await fetch(B + '/api/keywords/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({word:w})});
  loadKW();
}

async function loadPrefix(){
  const r = await fetch(B + '/api/prefix').then(r=>r.json());
  if(r.code!==0) return;
  const pb = el('pfbtn');
  pb.textContent = r.enabled ? '前缀功能：已开启（点击关闭）' : '前缀功能：已关闭（点击开启）';
  pb.style.background = r.enabled ? '#16a34a' : '#4b5563';
  const box = el('pflist');
  box.innerHTML = '';
  if(!r.prefixes.length){
    const hint = document.createElement('div'); hint.className='hint';
    hint.textContent = '（空）暂无专属前缀';
    box.appendChild(hint);
    return;
  }
  r.prefixes.forEach(function(item){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.textContent = item.qq + ' → ' + item.prefix;
    const btn = document.createElement('button'); btn.className='danger'; btn.textContent='删除';
    btn.onclick = function(){ delPrefix(item.qq); };
    row.appendChild(span); row.appendChild(btn);
    box.appendChild(row);
  });
}
async function togglePrefix(){
  const cur = el('pfbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/prefix/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})}).then(r=>r.json());
  if(r.code===0) loadPrefix(); else alert(r.message||'操作失败');
}
async function addPrefix(){
  const qq = el('pfqq').value.trim();
  const prefix = el('pftext').value.trim();
  const r = await fetch(B + '/api/prefix/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq:qq, prefix:prefix})}).then(r=>r.json());
  if(r.code===0){ el('pfqq').value=''; el('pftext').value=''; loadPrefix(); } else { alert(r.message||'添加失败'); }
}
async function delPrefix(qq){
  await fetch(B + '/api/prefix/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq:qq})});
  loadPrefix();
}

async function loadAuto(){
  const r = await fetch(B + '/api/auto').then(r=>r.json());
  if(r.code!==0) return;
  const btn = el('autobtn');
  btn.textContent = r.enabled ? '已开启（点击关闭）' : '已关闭（点击开启）';
  btn.style.background = r.enabled ? '#16a34a' : '#4b5563';
  el('autostate').textContent = r.users.length ? ('名单：' + r.users.length + ' 个 QQ') : '名单为空';
  const box = el('autolist');
  box.innerHTML = '';
  if(!r.users.length){
    const hint = document.createElement('div'); hint.className='hint';
    hint.textContent = '（空）还没有接话用户';
    box.appendChild(hint);
    return;
  }
  r.users.forEach(function(qq){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.textContent = qq;
    const del = document.createElement('button'); del.className='danger'; del.textContent='删除';
    del.onclick = function(){ delAuto(qq); };
    row.appendChild(span); row.appendChild(del);
    box.appendChild(row);
  });
  if(STK_DATA.length > STK_SHOWN){
    const more = document.createElement('button');
    more.textContent = '显示更多（还有 ' + (STK_DATA.length - STK_SHOWN) + ' 张）';
    more.style.marginTop = '8px';
    more.onclick = function(){ STK_SHOWN += 50; renderStkList(); };
    box.appendChild(more);
  }
}
async function toggleAuto(){
  const cur = el('autobtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/auto/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})}).then(r=>r.json());
  if(r.code===0) loadAuto();
}
async function addAuto(){
  const v = el('autoqq').value.trim(); if(!v) return;
  const r = await fetch(B + '/api/auto/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq:v})}).then(r=>r.json());
  if(r.code===0){ el('autoqq').value=''; loadAuto(); } else { alert(r.message||'添加失败'); }
}
async function delAuto(qq){
  await fetch(B + '/api/auto/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq:qq})});
  loadAuto();
}

async function loadEnd(){
  const r = await fetch(B + '/api/end-phrase').then(r=>r.json());
  if(r.code!==0) return;
  const b = el('endtoggle');
  b.textContent = r.enabled ? '结束语功能：已开启（点击关闭）' : '结束语功能：已关闭（点击开启）';
  b.style.background = r.enabled ? '#16a34a' : '#4b5563';
  el('endreply').value = r.reply || '';
  renderEndPhrases(r.phrases || []);
}
function renderEndPhrases(list){
  const box = el('endlist');
  box.innerHTML = '';
  if(!list.length){
    const h = document.createElement('div'); h.className='hint';
    h.textContent = '（空）没有触发词，功能相当于关闭';
    box.appendChild(h);
    return;
  }
  list.forEach(function(p){
    const row = document.createElement('div'); row.className='item';
    const sp = document.createElement('span'); sp.textContent = p;
    const del = document.createElement('button'); del.className='danger'; del.textContent='删除';
    del.onclick = function(){ delEndPhrase(p); };
    row.appendChild(sp); row.appendChild(del);
    box.appendChild(row);
  });
}
async function toggleEnd(){
  const cur = el('endtoggle').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/end-phrase/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})}).then(r=>r.json());
  if(r.code===0) loadEnd(); else alert(r.message||'操作失败');
}
async function saveEndReply2(){
  const r = await fetch(B + '/api/end-phrase/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reply: el('endreply').value})}).then(r=>r.json());
  el('endmsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('endmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadEnd();
}
async function addEndPhrase(){
  const v = el('endinput').value.trim(); if(!v) return;
  const r = await fetch(B + '/api/end-phrase/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phrase:v})}).then(r=>r.json());
  if(r.code===0){ el('endinput').value=''; loadEnd(); } else { alert(r.message||'添加失败'); }
}
async function delEndPhrase(p){
  await fetch(B + '/api/end-phrase/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phrase:p})});
  loadEnd();
}

let STK_DATA = [], STK_SHOWN = 50;
async function loadStickerPackInfo(){
  try{
    const r=await fetch(B+'/api/stickerpack/info').then(x=>x.json());
    if(r.code===0){
      el('stkpackinfo').textContent='本机共享令牌：'+r.token+'　地址：'+(r.base||'未设置公开地址')+'　共 '+r.count+' 张';
      if(!el('stkpackbase').value && r.base) el('stkpackbase').value=r.base;
    }
  }catch(e){}
}
async function repairStickers(){
  try{
    const r=await fetch(B+'/api/stickers/repair',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(x=>x.json());
    el('stkpackmsg').textContent=r.code===0?('修复完成，补登记 '+r.added+' 张'):(r.message||'失败');
    if(r.code===0) loadStickers();
  }catch(e){ el('stkpackmsg').textContent='网络错误'; }
}
async function importStickerPack(){
  const base=(el('stkpackbase').value||'').trim()||'https://xrzs.cloud';
  const token='';
  el('stkpackmsg').textContent='正在连接中心库…';
  const barEl=el('stkpackbar'), fillEl=el('stkpackfill');
  if(barEl) barEl.classList.add('show');
  if(fillEl) fillEl.style.width='3%';
  try{
    const r=await fetch(B+'/api/stickers/import_remote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base, token})}).then(x=>x.json());
    if(r.code!==0||!r.job){ el('stkpackmsg').textContent=r.message||'启动失败'; return; }
    const job=r.job;
    const timer=setInterval(async function(){
      try{
        const s=await fetch(B+'/api/stickers/import_status?job='+job).then(x=>x.json());
        const j=s.job||{};
        if(j.state==='running'){
          const pct=j.total?Math.min(99,Math.round(j.done/j.total*100)):5;
          if(fillEl) fillEl.style.width=pct+'%';
          el('stkpackmsg').textContent='同步中 '+j.done+'/'+(j.total||'?')+'（'+pct+'%），已新增 '+j.added+' 张…';
          return;
        }
        clearInterval(timer);
        if(j.state==='done'){
          if(fillEl) fillEl.style.width='100%';
          el('stkpackmsg').textContent='同步完成，新增 '+j.added+' 张（共 '+j.total+' 张）';
          setTimeout(function(){ if(barEl) barEl.classList.remove('show'); },1200);
          loadStickers();
        }
        else el('stkpackmsg').textContent='同步失败：'+(j.error||'未知');
      }catch(e){ clearInterval(timer); el('stkpackmsg').textContent='状态查询失败，请刷新看结果'; }
    },1500);
  }catch(e){ if(barEl) barEl.classList.remove('show'); el('stkpackmsg').textContent='网络错误'; }
}
async function loadStickers(){
  const r = await fetch(B + '/api/stickers').then(r=>r.json());
  if(r.code!==0) return;
  el('stkprob').value = r.probability;
  if(el('stkday')) el('stkday').value = r.daily_limit||12;
  el('skmrandom').style.background = (r.mode==='smart') ? '#4b5563' : '#2563eb';
  el('skmsmart').style.background = (r.mode==='smart') ? '#2563eb' : '#4b5563';
  el('stkbase').textContent = r.base ? ('当前表情包访问地址：' + r.base) : '提示：上传一张图后会自动记录访问地址';
  STK_DATA = r.stickers || [];
  STK_SHOWN = 50;
  renderStkList();
}
function renderStkList(){
  const r = { stickers: STK_DATA };
  const box = el('stklist');
  box.innerHTML = '';
  if(!r.stickers.length){
    const hint = document.createElement('div'); hint.className='hint';
    hint.textContent = '（空）还没有表情包';
    box.appendChild(hint);
    return;
  }
  r.stickers.slice(0, STK_SHOWN).forEach(function(it){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span');
    span.style.display='flex'; span.style.alignItems='center'; span.style.gap='8px';
    if(it.url){
      const img = document.createElement('img');
      img.src = it.url; img.loading = 'lazy'; img.decoding = 'async';
      img.style.width='44px'; img.style.height='44px';
      img.style.objectFit='contain'; img.style.background='#fff'; img.style.borderRadius='6px';
      span.appendChild(img);
    }
    const info = document.createElement('span');
    info.style.display='flex'; info.style.flexDirection='column'; info.style.gap='2px';
    const t = document.createElement('span'); t.textContent = it.name;
    info.appendChild(t);
    const d = document.createElement('span'); d.className='hint';
    d.style.fontSize='12px';
    d.textContent = it.description ? ('说明：' + it.description) : '说明：未设置（智能匹配不会用到）';
    info.appendChild(d);
    span.appendChild(info);
    row.appendChild(span);
    const ed = document.createElement('button'); ed.textContent='编辑说明'; ed.style.background='#4b5563';
    ed.onclick = function(){
      const v = prompt('表情包说明（用于智能匹配，2~10字或一句话）', it.description || '');
      if(v === null) return;
      fetch(B + '/api/stickers/desc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:it.name, description:v})}).then(function(){ loadStickers(); });
    };
    row.appendChild(ed);
    const del = document.createElement('button'); del.className='danger'; del.textContent='删除';
    del.onclick = function(){ delSticker(it.name); };
    row.appendChild(del);
    box.appendChild(row);
  });
  if(STK_DATA.length > STK_SHOWN){
    const more = document.createElement('button');
    more.textContent = '显示更多（还有 ' + (STK_DATA.length - STK_SHOWN) + ' 张）';
    more.style.marginTop = '8px';
    more.onclick = function(){ STK_SHOWN += 50; renderStkList(); };
    box.appendChild(more);
  }
}
async function setStickerMode(mode){
  const r = await fetch(B + '/api/stickers/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:mode})}).then(r=>r.json());
  if(r.code===0) loadStickers(); else alert(r.message||'操作失败');
}
async function uploadSticker(){
  const f = el('stkfile').files[0];
  if(!f){ alert('先选择一张图片'); return; }
  const fd = new FormData(); fd.append('file', f);
  const r = await fetch(B + '/api/stickers/upload',{method:'POST',body:fd}).then(r=>r.json()).catch(function(){ return {code:-1,message:'上传失败'}; });
  if(r.code===0){ el('stkfile').value=''; loadStickers(); } else { alert(r.message||'上传失败'); }
}
async function uploadStickerMany(){
  const files = el('stkfile').files;
  if(!files || !files.length){ alert('先选择图片（可多选）'); return; }
  const fd = new FormData();
  for(let i=0;i<files.length;i++) fd.append('files', files[i]);
  const r = await fetch(B + '/api/stickers/upload_many',{method:'POST',body:fd}).then(r=>r.json()).catch(function(){ return {code:-1}; });
  if(r.code!==0){ alert('上传失败'); return; }
  alert('批量上传完成：成功 ' + r.saved + ' 张' + (r.failed ? ('，失败 ' + r.failed + ' 张') : ''));
  el('stkfile').value='';
  loadStickers();
}
async function addStickerUrls(){
  const raw = el('stkurls').value || '';
  const urls = raw.split(String.fromCharCode(10)).map(function(s){ return s.trim(); }).filter(Boolean);
  if(!urls.length){ alert('先粘贴图片链接，一行一个'); return; }
  const r = await fetch(B + '/api/stickers/add_urls',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls:urls})}).then(r=>r.json()).catch(function(){ return {code:-1}; });
  if(r.code!==0){ alert('导入失败'); return; }
  alert('导入完成：成功 ' + r.saved + ' 张' + (r.failed ? ('，失败 ' + r.failed + ' 张') : ''));
  el('stkurls').value='';
  loadStickers();
}
async function delSticker(name){
  await fetch(B + '/api/stickers/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
  loadStickers();
}
async function installStickerPack(){
  const m = el('stkmsg');
  m.textContent = '正在开始导入…'; m.style.color = '#9aa4b8';
  try{
    const r = await fetch(B + '/api/stickers/install_pack', {method:'POST', headers:{'Content-Type':'application/json'},
      body:'{}'}).then(r=>r.json());
    if(r.code !== 0){ m.textContent = r.message || '导入失败'; m.style.color = '#f87171'; return; }
    let st = {}, fails = 0;
    for(let i = 0; i < 300; i++){
      await new Promise(function(res){ setTimeout(res, 2000); });
      try{
        const resp = await fetch(B + '/api/stickers/install_status');
        if(!resp.ok) throw new Error('HTTP ' + resp.status);
        st = await resp.json(); fails = 0;
      }catch(e){
        fails++;
        if(fails >= 3){ m.textContent = '状态获取失败，请刷新表情包列表确认是否已导入'; m.style.color = '#f87171'; return; }
        continue;
      }
      if(st.message) m.textContent = st.message + (st.running ? '（进行中… 已处理 ' + (st.added||0) + ' 张）' : '');
      if(st.done || (!st.running && st.message)) break;
    }
    m.style.color = st.done ? '#4ade80' : '#fbbf24';
    if(st.done) loadStickers && loadStickers();
  }catch(e){ m.textContent = '导入失败：' + e; m.style.color = '#f87171'; }
}
async function saveStickerProb(){
  const r = await fetch(B + '/api/stickers/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({probability: parseInt(el('stkprob').value||'0'), daily_limit: parseInt(el('stkday').value||'12')})}).then(r=>r.json());
  el('stkmsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('stkmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadStickers();
}

let SEG_MODE = 'fixed';
function setSegMode(m){
  SEG_MODE = (m === 'random') ? 'random' : 'fixed';
  el('segfixed').style.background = (SEG_MODE === 'fixed') ? '#2563eb' : '#4b5563';
  el('segrandom').style.background = (SEG_MODE === 'random') ? '#2563eb' : '#4b5563';
  applySegView();
}
function applySegView(){
  const fixed = SEG_MODE !== 'random';
  const fw = el('segfixedwrap'), r1 = el('segrandwrap1'), r2 = el('segrandwrap2');
  fw.style.display = fixed ? '' : 'none';
  r1.style.display = fixed ? 'none' : '';
  r2.style.display = fixed ? 'none' : '';
  const box = fixed ? fw : r1;
  if(box){
    box.classList.remove('seg-anim');
    void box.offsetWidth;
    box.classList.add('seg-anim');
  }
}
async function saveSegConfig(){
  const r = await fetch(B + '/api/group-rate/segconfig',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    mode: SEG_MODE,
    fixed: parseInt(el('segfixedn').value||'2'),
    min: parseInt(el('segmin').value||'1'),
    max: parseInt(el('segmax').value||'5')
  })}).then(r=>r.json());
  el('segmsg').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('segmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
}
async function saveSegTiming(){
  const r = await fetch(B + '/api/group-rate/segconfig',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    first_delay_ms: parseInt(el('segfirst').value||'300'),
    seg_delay_ms: parseInt(el('segdelay').value||'600'),
    sticker_delay_ms: parseInt(el('segsticker').value||'800')
  })}).then(r=>r.json());
  el('segmsg2').textContent = r.code===0 ? '已保存' : (r.message||'保存失败');
  el('segmsg2').style.color = r.code===0 ? '#4ade80' : '#f87171';
}
async function loadRate(){
  const r = await fetch(B + '/api/group-rate').then(r=>r.json());
  if(r.code!==0) return;
  el('ratedefault').textContent = '默认：每分钟最多 ' + r.default_max + ' 条，间隔 ' + r.default_min + ' 秒';
  el('segfixedn').value = r.seg_fixed;
  el('segfirst').value = r.first_delay_ms;
  el('segdelay').value = r.seg_delay_ms;
  el('segsticker').value = r.sticker_delay_ms;
  el('segmin').value = r.seg_min;
  el('segmax').value = r.seg_max;
  setSegMode(r.seg_mode || 'fixed');
  const box = el('ratelist');
  box.innerHTML = '';
  if(!r.groups.length){
    const hint = document.createElement('div'); hint.className='hint';
    hint.textContent = '白名单为空，暂无群可配置（先到「白名单」添加群号）';
    box.appendChild(hint);
    return;
  }
  r.groups.forEach(function(gid){
    const rate = r.rates.find(function(x){ return x.group_id === gid; });
    const row = document.createElement('div'); row.className='item'; row.style.flexWrap='wrap'; row.style.gap='6px';
    const span = document.createElement('span'); span.textContent = gid; span.style.minWidth='86px';
    const i1 = document.createElement('input'); i1.type='number'; i1.min='1'; i1.style.width='76px'; i1.placeholder='最多几条/分'; i1.value = rate ? rate.max_per_minute : '';
    const i2 = document.createElement('input'); i2.type='number'; i2.min='1'; i2.style.width='76px'; i2.placeholder='间隔几秒'; i2.value = rate ? rate.min_interval_seconds : '';
    const b = document.createElement('button'); b.textContent='保存'; b.onclick = function(){ saveRate(gid, i1.value, i2.value); };
    const b2 = document.createElement('button'); b2.className='danger'; b2.textContent='恢复默认'; b2.onclick = function(){ resetRate(gid); };
    row.appendChild(span); row.appendChild(i1); row.appendChild(i2); row.appendChild(b); row.appendChild(b2);
    box.appendChild(row);
  });
}
async function saveRate(gid, cap, interval){
  const r = await fetch(B + '/api/group-rate/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group_id:gid, max_per_minute:parseInt(cap||'6'), min_interval_seconds:parseInt(interval||'3')})}).then(r=>r.json());
  if(r.code===0){ loadRate(); } else { alert(r.message||'保存失败'); }
}
async function resetRate(gid){
  await fetch(B + '/api/group-rate/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group_id:gid})});
  loadRate();
}

async function loadMusic(){
  const r = await fetch(B + '/api/music?_=' + Date.now()).then(r=>r.json());
  if(r.code!==0) return;
  el('musicbtn').textContent = r.enabled ? '音乐分享：已开启' : '音乐分享：已关闭';
  el('musicbtn').style.background = r.enabled ? '#16a34a' : '#4b5563';
}
async function toggleMusic(){
  const cur = el('musicbtn').textContent.indexOf('已开启') !== -1;
  await fetch(B + '/api/music/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur})});
  loadMusic();
}
async function loadGR(){
  const r = await fetch(B + '/api/group-reply').then(r=>r.json());
  if(r.code!==0) return;
  loadConvos();
  el('grsecs').value = r.continue_seconds;
  el('grcap').value = r.max_replies;
  el('gramax').value = r.max_active_users;
  const tb = el('thriftbtn');
  tb.textContent = r.thrifty ? '省流模式：已开启（只回@/关键词）' : '省流模式：已关闭';
  tb.style.background = r.thrifty ? '#16a34a' : '#4b5563';
  const ab = el('atreplybtn');
  ab.textContent = r.at_reply ? '被@时回复@对方：已开启' : '被@时回复@对方：已关闭';
  ab.style.background = r.at_reply ? '#16a34a' : '#4b5563';
  if(r.whitelist_empty){
    el('grhint').textContent = '白名单为空：当前对全部群聊生效，下面显示的是近期收到过消息的群。建议先去白名单添加群。';
  } else {
    el('grhint').textContent = '接话时间：机器人说过话后，这段时间内群消息免 @ 继续接话（秒）。频率：每分钟最多回复条数。';
  }
  const box = el('grlist');
  box.innerHTML = '';
  if(!r.groups.length){
    const hint = document.createElement('div'); hint.className='hint';
    hint.textContent = '（暂无群）白名单为空时默认全部群聊生效';
    box.appendChild(hint);
    return;
  }
  r.groups.forEach(function(gid){
    const on = r.always.indexOf(gid) !== -1;
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.textContent = gid;
    const btn = document.createElement('button');
    btn.textContent = on ? '一直接话：开' : '一直接话：关';
    btn.style.background = on ? '#16a34a' : '#4b5563';
    btn.onclick = function(){ toggleGRAlways(gid, !on); };
    row.appendChild(span); row.appendChild(btn);
    box.appendChild(row);
  });
}
async function loadConvos(){
  const r = await fetch(B + '/api/conversations').then(r=>r.json());
  if(r.code!==0) return;
  const box = el('convlist');
  box.innerHTML = '';
  if(!r.items.length){
    const hint = document.createElement('div'); hint.className='hint';
    hint.textContent = '（空）当前没有接话中的用户';
    box.appendChild(hint);
    return;
  }
  r.items.forEach(function(it){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span');
    span.textContent = '群 ' + it.group_id + ' · QQ ' + it.qq + ' · 剩余 ' + it.expires_in + ' 秒';
    const del = document.createElement('button'); del.className='danger'; del.textContent='删除';
    del.onclick = function(){ removeConvo(it.group_id, it.qq); };
    row.appendChild(span); row.appendChild(del); box.appendChild(row);
  });
}
async function saveGRConfig(){
  const r = await fetch(B + '/api/group-reply/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({continue_seconds: parseInt(el('grsecs').value||'180'), max_replies: parseInt(el('grcap').value||'6'), max_active_users: parseInt(el('gramax').value||'3')})}).then(r=>r.json());
  el('grmsg').textContent = r.code===0 ? '已保存，立即生效' : (r.message||'保存失败');
  el('grmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
}
async function removeConvo(gid, qq){
  const r = await fetch(B + '/api/conversations/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group_id:gid, qq:qq})}).then(r=>r.json());
  if(r.code===0) loadConvos(); else alert(r.message||'删除失败');
}

async function toggleAtReply(){
  const cur = el('atreplybtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/group-reply/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({at_reply: !cur})}).then(r=>r.json());
  if(r.code===0) loadGR(); else alert(r.message||'操作失败');
}
async function toggleThrift(){
  const cur = el('thriftbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/group-reply/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({thrifty: !cur})}).then(r=>r.json());
  if(r.code===0) loadGR(); else alert(r.message||'操作失败');
}
async function toggleGRAlways(gid, enabled){
  const r = await fetch(B + '/api/group-reply/always',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group_id:gid, enabled:enabled})}).then(r=>r.json());
  if(r.code===0) loadGR(); else alert(r.message||'操作失败');
}

async function loadBored(){
  const r = await fetch(B + '/api/bored').then(r=>r.json());
  if(r.code!==0) return;
  const btn = el('boredbtn');
  btn.textContent = r.enabled ? '已开启（点击关闭）' : '已关闭（点击开启）';
  btn.style.background = r.enabled ? '#16a34a' : '#4b5563';
  el('boredstate').textContent = r.enabled ? '群聊安静太久会主动冒泡' : '不会主动冒泡';
  el('boredmin').value = r.min_minutes;
  el('boredfixed').value = r.interval_minutes;
  el('btf').style.background = (r.time_mode==='fixed') ? '#2563eb' : '#4b5563';
  el('btr').style.background = (r.time_mode==='fixed') ? '#4b5563' : '#2563eb';
  el('boredmax').value = r.max_minutes;
  el('boredfloor').value = r.floor_minutes;
  el('modepool').style.background = (r.mode==='ai') ? '#4b5563' : '#2563eb';
  el('modeai').style.background = (r.mode==='ai') ? '#2563eb' : '#4b5563';
  loadBoredLines();
}
async function setBoredMode(mode){
  const r = await fetch(B + '/api/bored/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode: mode})}).then(r=>r.json());
  if(r.code===0) loadBored(); else alert(r.message||'操作失败');
}
async function loadBoredLines(){
  const r = await fetch(B + '/api/bored/lines').then(r=>r.json());
  if(r.code!==0) return;
  const box = el('bllist');
  box.innerHTML = '';
  if(!r.lines.length){
    const hint = document.createElement('div'); hint.className='hint';
    hint.textContent = '（空）静态模式将使用内置兜底语料';
    box.appendChild(hint);
    return;
  }
  r.lines.forEach(function(line){
    const row = document.createElement('div'); row.className='item';
    const span = document.createElement('span'); span.textContent = line;
    const del = document.createElement('button'); del.className='danger'; del.textContent='删除';
    del.onclick = function(){ delBoredLine(line); };
    row.appendChild(span); row.appendChild(del);
    box.appendChild(row);
  });
  if(STK_DATA.length > STK_SHOWN){
    const more = document.createElement('button');
    more.textContent = '显示更多（还有 ' + (STK_DATA.length - STK_SHOWN) + ' 张）';
    more.style.marginTop = '8px';
    more.onclick = function(){ STK_SHOWN += 50; renderStkList(); };
    box.appendChild(more);
  }
}
async function addBoredLine(){
  const v = el('blinput').value.trim(); if(!v) return;
  const r = await fetch(B + '/api/bored/lines/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({line:v})}).then(r=>r.json());
  if(r.code===0){ el('blinput').value=''; loadBoredLines(); } else { alert(r.message||'添加失败'); }
}
async function delBoredLine(line){
  await fetch(B + '/api/bored/lines/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({line:line})});
  loadBoredLines();
}
async function toggleBored(){
  const cur = el('boredbtn').textContent.indexOf('已开启') !== -1;
  const r = await fetch(B + '/api/bored/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled: !cur, interval_minutes: parseInt(el('boredmin').value||'30')})}).then(r=>r.json());
  if(r.code===0) loadBored(); else alert(r.message||'操作失败');
}
async function setBoredTimeMode(mode){
  const r = await fetch(B + '/api/bored/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({time_mode: mode})}).then(r=>r.json());
  if(r.code===0) loadBored(); else alert(r.message||'操作失败');
}
async function saveBoredInterval(){
  const r = await fetch(B + '/api/bored/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    min_minutes: parseInt(el('boredmin').value||'30'),
    max_minutes: parseInt(el('boredmax').value||'60'),
    floor_minutes: parseInt(el('boredfloor').value||'30'),
    interval_minutes: parseInt(el('boredfixed').value||el('boredmin').value||'30')
  })}).then(r=>r.json());
  el('boredmsg').textContent = r.code===0 ? '已保存，到点生效' : (r.message||'保存失败');
  el('boredmsg').style.color = r.code===0 ? '#4ade80' : '#f87171';
  if(r.code===0) loadBored();
}

async function loadAdmins(){
  const r = await fetch(B + '/api/admins').then(r=>r.json());
  if(r.code!==0) return;
  renderList('alist', r.admins, delAdmin, '（空）');
}
async function delAdmin(u){
  const r = await fetch(B + '/api/admins/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u})}).then(r=>r.json());
  if(r.code!==0){ alert(r.message||'删除失败'); } else { loadAdmins(); }
}

(function(){
  const hint = document.getElementById('swipehint');
  const tabs = document.getElementById('tabs');
  if(!hint || !tabs) return;
  const hide = function(){ hint.style.display = 'none'; };
  if(tabs.scrollWidth <= tabs.clientWidth + 4){ hide(); return; }
  tabs.addEventListener('scroll', function(){ if(tabs.scrollLeft > 8) hide(); }, {passive:true});
  setTimeout(hide, 8000);
})();
