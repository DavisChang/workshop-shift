'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const iso = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const parse = s => new Date(s+'T12:00:00');
const plus = (s,n) => {const d=parse(s);d.setDate(d.getDate()+n);return iso(d)};
const monday = s => plus(s,-((parse(s).getDay()+6)%7));
let week=monday(iso(new Date())), view='schedule', state=null, busy=false, timer;
// Teaching preferences stay in this browser; no scheduling data is changed.
const helpStorageKey = 'workshop-shift.help-enabled';
let helpEnabled = true, helpAnchor = null;
try { helpEnabled = localStorage.getItem(helpStorageKey) !== 'false'; } catch (_) {}
const helpTopics = [
  ['#generate', '自動安排本週', '依三種職務的每日需求安排人力，避開請假並遵守每週上限。重排既有班表會保留今天以前的安排，今天起的手動安排則會被取代；人手不足會顯示缺額。'],
  ['#week-picker', '查看不同週別', '用左右箭頭切換週別，或挑選任一天跳至該週。按「本週」回到現在；班表與請假紀錄都依選定週別顯示。'],
  ['.stats .stat:last-child .stat-label', '看懂待補人力', '這是本週各日、各職務缺額的總人次，不是缺少幾位不同員工。例如同一天缺 2 位櫃檯，就計為 2 人次。請查看表格橘色缺額，再補人或調整安排。'],
  ['.panel-bottom > span:first-child', '手動調整班次', '點選表格中的「出勤」或「休息」即可切換。請假日與停用人員無法排班，超過每週出勤上限也會被阻擋。變更會立即儲存，不需要另外按儲存。'],
  ['a[href^="/api/export"]', '帶走這週的班表', '匯出目前選定週別的 CSV，包含姓名、職務、每日出勤時間、請假與出勤天數。可用 Excel 或其他試算表開啟；下載不會修改班表。'],
  ['#leave-form .muted', '登記整日請假', '選擇人員與起訖日期，開始日和結束日都算請假。送出即生效，跨週的衝突班次也會移除；之後請到相關週別檢查缺額並重新排班。'],
  ['[data-cancel-leave]', '取消請假之後', '取消這筆請假後，人員會重新成為可排班對象，但被移除的班次不會自動恢復。請回到該週手動補班或重新排班。'],
  ['#person-form h2', '建立服務團隊', '填寫姓名並選擇職務即可新增人員。下方卡片可改名、停用或恢復人員。既有人員的職務固定，轉換職務時請停用後新增。'],
  ['[data-toggle-person]', '停用與恢復人員', '停用會移除今天起的班次，保留過去安排與請假紀錄；可能因此出現缺額。恢復在職後可重新排班，不會自動補回原班次。'],
  ['#settings-form button', '儲存前先確認規則', '每日最低需求與班段適用所有週別，修改時間也會影響歷史班表顯示。降低每週上限若與本週或未來班表衝突，系統會列出需要先調整的週別。每週上限不限制跨週連續工作天數。']
];

function closeHelp(restoreFocus = false) {
  const anchor = helpAnchor;
  $('#help-popup').hidden = true;
  helpAnchor = null;
  if (anchor) anchor.setAttribute('aria-expanded', 'false');
  if (restoreFocus && anchor?.isConnected) anchor.focus();
}

function positionHelp() {
  if (!helpAnchor?.isConnected) { closeHelp(); return; }
  const popup = $('#help-popup'), rect = helpAnchor.getBoundingClientRect();
  const width = document.documentElement.clientWidth, height = window.innerHeight;
  const left = Math.max(12, Math.min(rect.left, width - popup.offsetWidth - 12));
  const below = rect.bottom + 10;
  const top = below + popup.offsetHeight <= height - 12 ? below : Math.max(12, rect.top - popup.offsetHeight - 10);
  popup.style.left = left + 'px';
  popup.style.top = top + 'px';
}

function mountHelp() {
  closeHelp();
  document.querySelectorAll('[data-help-trigger]').forEach(button => button.remove());
  $('#help-toggle').textContent = helpEnabled ? '教學提示：開啟' : '教學提示：關閉';
  $('#help-toggle').setAttribute('aria-pressed', String(helpEnabled));
  if (!helpEnabled) return;
  helpTopics.forEach(([selector, title, description]) => {
    const target = document.querySelector(selector);
    if (!target || target.hidden) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'help-trigger';
    button.dataset.helpTrigger = '';
    button.textContent = '?';
    button.setAttribute('aria-label', '教學：' + title);
    button.setAttribute('aria-controls', 'help-popup');
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', () => {
      if (helpAnchor === button) { closeHelp(); return; }
      closeHelp();
      helpAnchor = button;
      $('#help-title').textContent = title;
      $('#help-description').textContent = description;
      $('#help-popup').hidden = false;
      button.setAttribute('aria-expanded', 'true');
      positionHelp();
      $('#help-close').focus({preventScroll: true});
    });
    target.insertAdjacentElement('afterend', button);
  });
}

function setHelpEnabled(enabled) {
  helpEnabled = enabled;
  try { localStorage.setItem(helpStorageKey, String(enabled)); } catch (_) {}
  mountHelp();
}

$('#help-toggle').addEventListener('click', () => setHelpEnabled(!helpEnabled));
$('#help-close').addEventListener('click', () => closeHelp(true));
$('#help-disable').addEventListener('click', () => { setHelpEnabled(false); $('#help-toggle').focus(); });
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && helpAnchor) { event.preventDefault(); closeHelp(true); }
});
document.addEventListener('click', event => {
  if (helpAnchor && !$('#help-popup').contains(event.target) && !helpAnchor.contains(event.target)) closeHelp();
});
document.addEventListener('focusin', event => {
  if (helpAnchor && !$('#help-popup').contains(event.target) && !helpAnchor.contains(event.target)) closeHelp();
});
window.addEventListener('resize', () => closeHelp());
window.addEventListener('scroll', event => {
  if (!$('#help-popup').contains(event.target)) closeHelp();
}, true);
window.addEventListener('storage', event => {
  if (event.key === helpStorageKey || event.key === null) {
    helpEnabled = event.newValue !== 'false';
    mountHelp();
  }
});
mountHelp();
const titles={schedule:['每週排班','讓每一天，都有人在。','掌握團隊出勤、安排服務量能，從一張清楚的班表開始。'],leaves:['請假管理','為團隊，留一點彈性。','登記整日請假，衝突班次會立即移除，缺額即時可見。'],people:['服務團隊','每個角色，都是關鍵。','管理櫃檯、技師與現場接待，讓服務始終有人接力。'],settings:['排班規則','訂好規則，安排更從容。','設定每日最低需求與每週上限，讓排班符合現場節奏。']};
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await r.json();if(!r.ok)throw Error(data.error||'操作失敗');return data}
function error(e){$('#error').textContent=e.message;$('#error').hidden=false}
function toast(text){clearTimeout(timer);$('#toast').textContent=text;$('#toast').hidden=false;timer=setTimeout(()=>$('#toast').hidden=true,5000)}
async function refresh(){state=await api('/api/state?week='+week);week=state.week;$('#loading').hidden=true;$('#app').hidden=false;render()}
async function act(path,body){if(busy)return;busy=true;$('#error').hidden=true;const buttons=[...document.querySelectorAll('button')].filter(b=>!b.matches('.help-trigger,#help-toggle,#help-close,#help-disable')).map(b=>[b,b.disabled]);buttons.forEach(([b])=>b.disabled=true);try{const r=await api(path,body);await refresh();toast(r.message)}catch(e){error(e)}finally{busy=false;buttons.forEach(([b,disabled])=>b.disabled=disabled)}}
async function confirmAction(title,description){const dialog=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-description').textContent=description;dialog.returnValue='cancel';dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true}))}
const active=()=>state.employees.filter(e=>e.active);
const onLeave=(id,d)=>state.leaves.some(l=>l.employee_id===id&&l.start_date<=d&&l.end_date>=d);
const working=(id,d)=>state.assignments.some(a=>a.employee_id===id&&a.date===d);
const total=id=>state.assignments.filter(a=>a.employee_id===id).length;
function weekControls(){return `<div class="week-controls"><button data-week="-7" aria-label="上一週">‹</button><button data-week="7" aria-label="下一週">›</button><span class="week-range">${week.replaceAll('-','.')} — ${plus(week,6).slice(5).replace('-','.')}</span><button data-week="today">本週</button><input type="date" id="week-picker" value="${week}" aria-label="跳至指定日期所在週"></div>`}
function schedule(){const missing=state.coverage.reduce((n,c)=>n+c.missing,0), needed=state.coverage.reduce((n,c)=>n+c.needed,0), fulfilled=state.coverage.reduce((n,c)=>n+Math.min(c.actual,c.needed),0), coverage=Math.round(fulfilled/needed*100), days=Array.from({length:7},(_,i)=>plus(week,i));const leavePeople=new Set(state.leaves.map(l=>l.employee_id)).size;return `<div class="stats">${[['在職團隊',active().length,'人','櫃檯 / 技師 / 現場接待','♙'],['本週已排',state.assignments.length,'人次','每人每週最多 '+state.settings.max_days+' 天','▦'],['本週請假',leavePeople,'人',state.leaves.length+' 筆請假紀錄','◷'],['待補人力',missing,'人次',missing?'仍有班次需要你的安排':'本週服務人力已充足','↗']].map((s,i)=>`<div class="stat ${i===3&&missing?'warning':''}"><span class="stat-label">${s[0]}</span><span class="stat-icon">${s[4]}</span><div class="stat-number">${s[1]}<small>${s[2]}</small></div><div class="stat-note">${s[3]}</div></div>`).join('')}</div>
${missing?`<div class="alert"><span>△</span><div><strong>${state.assignments.length?'尚有 '+missing+' 人次缺額，服務需要支援。':'這週還有 '+missing+' 人次待安排。'}</strong><p>${state.generated_at?'自動排班已依可用人力安排；請檢查橘色缺額，可新增人員、調整需求或取消請假後重排。':'點選「自動排班」開始；系統會避開請假，並遵守每週出勤上限。'}</p></div></div>`:`<div class="alert success"><span>✓</span><div><strong>本週七天，服務人力均已到位。</strong><p>每日三種職務都達到最低需求；異動後仍會即時檢查缺額。</p></div></div>`}
<div class="panel"><div class="panel-heading">${weekControls()}<div class="toolbar-right"><div class="legend"><span><i></i>出勤</span><span><i class="off"></i>休息</span><span><i class="leave"></i>請假</span></div><a class="secondary" href="/api/export?week=${week}">↓ 匯出 CSV</a></div></div><div class="table-scroll"><table><thead><tr><th>團隊成員 <small>TEAM MEMBERS</small></th>${days.map((d,i)=>`<th class="${d===iso(new Date())?'today':''}">${['週一','週二','週三','週四','週五','週六','週日'][i]}<small>${d.slice(5).replace('-',' / ')}</small></th>`).join('')}<th>合計<small>天 / 週</small></th></tr></thead><tbody>${Object.entries(state.roles).map(([role,label])=>{const staff=state.employees.filter(e=>e.role===role&&(e.active||total(e.id)));return `<tr class="group-row"><td colspan="9">${label}<span>${staff.length} 人 · 每日需 ${state.settings.needs[role]} 人</span></td></tr>${staff.map(e=>`<tr><td><div class="person-name"><span class="avatar">${esc(e.name.slice(-2))}</span>${esc(e.name)}${e.active?'':'（停用）'}</div></td>${days.map(d=>{const leave=onLeave(e.id,d),work=working(e.id,d);return `<td><button class="shift ${leave?'leave':work?'':'off'}" data-shift="${e.id}" data-date="${d}" ${leave||!e.active?'disabled':''} aria-label="${esc(e.name)} ${d} ${leave?'請假':work?'出勤，點選取消':'休息，點選排班'}">${leave?'請假':work?state.settings.start_time+'–'+state.settings.end_time:'休息'}</button></td>`}).join('')}<td class="count">${total(e.id)} <span class="muted">/ ${state.settings.max_days}</span></td></tr>`).join('')}<tr class="coverage-row"><td>${label} · 每日到位</td>${days.map(d=>{const c=state.coverage.find(c=>c.role===role&&c.date===d);return `<td class="${c.missing?'short':''}">${c.actual} / ${c.needed} ${c.missing?'· 缺 '+c.missing:'✓'}</td>`}).join('')}<td></td></tr>`}).join('')}</tbody></table></div><div class="panel-bottom"><span>點選班次即可切換出勤 / 休息；請假日無法排班。</span><span>${state.generated_at?'最近自動排班 '+esc(state.generated_at.replace('T',' ')):'尚未自動產生本週班表'}</span></div></div>
<div class="bottom-grid"><div class="summary-card"><h2>本週服務覆蓋 <span class="muted">${coverage}%</span></h2>${Object.entries(state.roles).map(([r,l])=>{const cs=state.coverage.filter(c=>c.role===r),a=cs.reduce((n,c)=>n+Math.min(c.actual,c.needed),0),b=state.settings.needs[r]*7;return `<div class="role-summary"><span>${l}</span><progress class="progress" value="${a}" max="${b}" aria-label="${l}服務覆蓋"></progress><strong>${a} / ${b} 人次</strong></div>`}).join('')}</div><div class="summary-card"><h2>本週排班原則</h2><ul class="note-list"><li>週一至週日營業 · ${state.settings.start_time}–${state.settings.end_time} 單班</li><li>每人每週最多 ${state.settings.max_days} 天，優先平衡出勤天數</li><li>請假自動排除；人力不足時保留缺額，不超排</li></ul></div></div>`}
function leaves(){return `<div class="forms-grid"><div class="panel"><div class="panel-heading"><span class="panel-title">新增整日請假</span></div><form id="leave-form" class="form"><label>請假人員<select name="employee_id" required>${active().map(e=>`<option value="${e.id}">${esc(e.name)} · ${state.roles[e.role]}</option>`).join('')}</select></label><label>開始日期<input type="date" name="start_date" value="${week}" required></label><label>結束日期<input type="date" name="end_date" value="${week}" required></label><label>備註（選填）<input name="reason" maxlength="200" placeholder="例如：特休、個人事務"></label><p class="muted">登記即生效；該日期範圍的既有班次會移除，其他班次保留。</p><button class="primary">登記請假</button></form></div><div class="panel"><div class="panel-heading"><span class="panel-title">本週請假紀錄</span>${weekControls()}</div><div class="list">${state.leaves.length?state.leaves.map(l=>`<div class="list-item"><div><strong>${esc(state.employees.find(e=>e.id===l.employee_id)?.name||'未知人員')}</strong><p>${l.start_date} — ${l.end_date}</p><p>${esc(l.reason||'未填寫備註')}</p></div><button class="secondary" data-cancel-leave="${l.id}">取消請假</button></div>`).join(''):'<div class="empty">本週沒有請假紀錄，團隊準備就緒。</div>'}</div></div></div>`}
function people(){return `<div class="panel"><form id="person-form" class="form"><h2>新增團隊成員</h2><div class="field-row"><label>姓名<input name="name" required maxlength="40" placeholder="輸入人員姓名"></label><label>職務<select name="role">${Object.entries(state.roles).map(([r,l])=>`<option value="${r}">${l}</option>`).join('')}</select></label></div><button class="primary">新增人員</button></form></div><div class="people-grid">${state.employees.map(e=>`<article class="person-card ${e.active?'':'inactive'}"><header><span class="avatar">${esc(e.name.slice(-2))}</span><div><h2>${esc(e.name)}</h2><p>${state.roles[e.role]} · ${e.active?'在職':'已停用'}</p></div></header><form class="rename-row" data-rename="${e.id}"><input class="edit-name" name="name" value="${esc(e.name)}" maxlength="40" required aria-label="${esc(e.name)}的新姓名"><button class="secondary">改名</button></form><button class="secondary" data-toggle-person="${e.id}">${e.active?'停用人員':'恢復在職'}</button></article>`).join('')}</div>`}
function settings(){const s=state.settings;return `<div class="settings-wrap"><div class="panel"><div class="panel-heading"><span class="panel-title">每日服務量能</span><span class="week-tag">週一至週日適用</span></div><form id="settings-form" class="form">${Object.entries(state.roles).map(([r,l])=>`<label>${l} · 每日最低人數<input type="number" name="${r}" min="1" max="20" value="${s.needs[r]}" required></label>`).join('')}<label>每人每週最多出勤天數<input type="number" name="max_days" min="1" max="7" value="${s.max_days}" required></label><div class="field-row"><label>上班時間<input type="time" name="start_time" value="${s.start_time}" required></label><label>下班時間<input type="time" name="end_time" value="${s.end_time}" required></label></div><button class="primary">儲存規則</button></form><div class="settings-note">規則對所有週別生效；修改時間會同步顯示於既有班表。降低出勤上限前，須先取消超出上限的既有班次。<br>目前為整日單班排程，未計算休息時段、跨週連續出勤或勞動法規；請依車廠實際制度確認安排。</div></div></div>`}
function render(){const t=titles[view];$('#breadcrumb').textContent=t[0];$('#page-title').textContent=t[1];$('#page-subtitle').textContent=t[2];$('#generate').hidden=view!=='schedule';document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));$('#app').innerHTML=({schedule,leaves,people,settings}[view])();bind();mountHelp()}
function bind(){document.querySelectorAll('[data-week]').forEach(b=>b.onclick=()=>changeWeek(b.dataset.week==='today'?iso(new Date()):plus(week,Number(b.dataset.week))));if($('#week-picker'))$('#week-picker').onchange=e=>{if(e.target.value)changeWeek(e.target.value)};document.querySelectorAll('[data-shift]').forEach(b=>b.onclick=()=>act('/api/assignment',{employee_id:Number(b.dataset.shift),date:b.dataset.date,working:!working(Number(b.dataset.shift),b.dataset.date)}));
if($('#leave-form'))$('#leave-form').onsubmit=e=>{e.preventDefault();const b=Object.fromEntries(new FormData(e.target));b.employee_id=Number(b.employee_id);act('/api/leaves',b)};
document.querySelectorAll('[data-cancel-leave]').forEach(b=>b.onclick=async()=>{if(await confirmAction('取消這筆請假？','取消後不會自動恢復班次；你可以重新排班或手動補入。'))act('/api/leaves/delete',{id:Number(b.dataset.cancelLeave)})});
if($('#person-form'))$('#person-form').onsubmit=e=>{e.preventDefault();act('/api/employees',Object.fromEntries(new FormData(e.target)))};
document.querySelectorAll('[data-rename]').forEach(f=>f.onsubmit=e=>{e.preventDefault();const p=state.employees.find(p=>p.id===Number(f.dataset.rename));act('/api/employees',{id:p.id,name:new FormData(f).get('name'),role:p.role,active:!!p.active})});
document.querySelectorAll('[data-toggle-person]').forEach(b=>b.onclick=async()=>{const p=state.employees.find(p=>p.id===Number(b.dataset.togglePerson));if(await confirmAction(p.active?'停用 '+p.name+'？':'恢復 '+p.name+'？',p.active?'今天起的班次會移除，歷史資料與請假保留。請檢查因此產生的缺額。':'恢復後可在下一次排班時安排出勤。'))act('/api/employees',{id:p.id,name:p.name,role:p.role,active:!p.active})});
if($('#settings-form'))$('#settings-form').onsubmit=e=>{e.preventDefault();const f=Object.fromEntries(new FormData(e.target));act('/api/settings',{needs:Object.fromEntries(Object.keys(state.roles).map(r=>[r,Number(f[r])])),max_days:Number(f.max_days),start_time:f.start_time,end_time:f.end_time})}}
async function changeWeek(value){if(busy)return;busy=true;const previous=week;week=monday(value);try{await refresh();$('#error').hidden=true}catch(e){week=previous;error(e)}finally{busy=false}}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{if(!state||busy)return;view=b.dataset.view;$('#error').hidden=true;render()});
$('#generate').onclick=async()=>{if(!state||busy)return;if((state.assignments.length||state.generated_at)&&!await confirmAction('重新產生本週班表？','今天起的手動安排將被取代；今天以前的既有安排保留。系統會依目前請假與規則重排，其他週不受影響。'))return;act('/api/generate',{week})};
refresh().catch(e=>{$('#loading').hidden=true;error(e)});
