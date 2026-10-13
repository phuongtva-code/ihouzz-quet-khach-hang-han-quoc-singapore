/* ===== Kho dữ liệu cục bộ (chế độ file) =====
   Dùng khi trang chạy NGOÀI claude.ai (GitHub Pages, mở local). Giả lập đúng phần API mà
   data.js dùng của window.claude.use('db' | 'user' | 'sample'):
     db.collection(c).onSnapshot(cb, err) · .doc(id).set(d) · .update(d) · .delete()
     user.id() · user.can('data.write')          sample: không có -> data.js dùng nhãn tạm bằng luật
   Dữ liệu nằm trong localStorage của trình duyệt đang dùng (khóa ihz_localdb_v1): mỗi máy một kho,
   không dùng chung trong team. Có nút Sao lưu / Khôi phục (.json) ở Màn 05 để chuyển kho giữa các máy.
   Trên claude.ai (đã có window.claude) file này không làm gì. */
(function(){
'use strict';
if(window.claude&&window.claude.use){return;}

var KEY='ihz_localdb_v1',COLLS=['sources','orgs','stats','signals'];
var mem=null,persistent=true,warned=false,listeners={};

function fresh(){var m={};COLLS.forEach(function(c){m[c]={};});return m;}
function load(){
  if(mem){return mem;}
  mem=fresh();
  try{var raw=localStorage.getItem(KEY);if(raw){var o=JSON.parse(raw);COLLS.forEach(function(c){if(o&&o[c]&&typeof o[c]==='object'){mem[c]=o[c];}});}}
  catch(e){persistent=false;}
  return mem;
}
function save(){
  try{localStorage.setItem(KEY,JSON.stringify(load()));persistent=true;return null;}
  catch(e){persistent=false;return e;}
}
function clone(o){return JSON.parse(JSON.stringify(o===undefined?null:o));}
function snap(c){var m=load()[c]||{};return {docs:Object.keys(m).map(function(id){return {id:id,data:function(){return clone(m[id]);}};})};}
function notify(c){(listeners[c]||[]).forEach(function(fn){try{fn(snap(c));}catch(e){}});}
function notifyAll(){COLLS.forEach(notify);}
function quotaError(e){var er=new Error('Kho trong trình duyệt đã đầy hoặc bị chặn (chế độ ẩn danh?). Hãy Sao lưu rồi Xóa bớt dữ liệu cũ.');er.code='quota_exceeded';er.cause=e;return er;}
function write(c,fn){
  return new Promise(function(res,rej){
    try{fn();}catch(e){rej(e);return;}
    var err=save();
    if(err){rej(quotaError(err));return;}
    notify(c);res();
  });
}
function collection(c){
  var m=load();if(!m[c]){m[c]={};}
  return {
    onSnapshot:function(cb,onErr){
      (listeners[c]=listeners[c]||[]).push(cb);
      setTimeout(function(){try{cb(snap(c));}catch(e){if(onErr){onErr(e);}}},0);
      return function(){listeners[c]=(listeners[c]||[]).filter(function(f){return f!==cb;});};
    },
    get:function(){return Promise.resolve(snap(c));},
    doc:function(id){
      id=String(id);
      return {
        set:function(d){return write(c,function(){load()[c][id]=clone(d||{});});},
        update:function(d){return write(c,function(){var row=load()[c][id];if(!row){var er=new Error('Không có bản ghi '+id);er.code='not_found';throw er;}Object.assign(row,clone(d||{}));});},
        delete:function(){return write(c,function(){delete load()[c][id];});},
        get:function(){var row=load()[c][id];return Promise.resolve({id:id,exists:!!row,data:function(){return row?clone(row):undefined;}});}
      };
    }
  };
}
var db={collection:collection};
var user={id:function(){return Promise.resolve('local');},can:function(){return Promise.resolve(true);}};
window.claude={use:function(name){
  if(name==='db'){return Promise.resolve(db);}
  if(name==='user'){return Promise.resolve(user);}
  return Promise.resolve(null);   // 'sample' (Claude phân loại) không có ở đây
}};

/* ---- tiện ích cho người dùng: đếm, sao lưu, khôi phục, xóa ---- */
function counts(){var m=load(),r={};COLLS.forEach(function(c){r[c]=Object.keys(m[c]||{}).length;});return r;}
function exportJSON(){return JSON.stringify({app:'ihouzz-quet-cong-dong',version:1,exportedAt:new Date().toISOString(),data:load()},null,0);}
function importJSON(text,replace){
  var o;try{o=JSON.parse(text);}catch(e){throw new Error('File không phải JSON hợp lệ.');}
  var data=o&&o.data&&typeof o.data==='object'?o.data:o;
  if(!data||typeof data!=='object'||!COLLS.some(function(c){return data[c]&&typeof data[c]==='object';})){throw new Error('File không đúng định dạng sao lưu (thiếu sources/orgs/stats/signals).');}
  var m=load(),added=0;
  if(replace){mem=fresh();m=mem;}
  COLLS.forEach(function(c){var src=data[c]||{};Object.keys(src).forEach(function(id){if(src[id]&&typeof src[id]==='object'){if(!m[c][id]){added++;}m[c][id]=clone(src[id]);}});});
  var err=save();if(err){throw quotaError(err);}
  notifyAll();return added;
}
function clearAll(){mem=fresh();try{localStorage.removeItem(KEY);}catch(e){}notifyAll();}
window.__localdb={counts:counts,exportJSON:exportJSON,importJSON:importJSON,clear:clearAll,get persistent(){return persistent;},KEY:KEY};

/* ---- tải file về máy ---- */
function download(name,text,mime){
  var blob=new Blob([text],{type:(mime||'text/plain')+';charset=utf-8'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();
  setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},1500);
}
function csvCell(v){v=v==null?'':String(v);return /[",\n\r;]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;}
function csv(rows){return '﻿'+rows.map(function(r){return r.map(csvCell).join(',');}).join('\r\n');}
function today(){var d=new Date();function p(n){return ('0'+n).slice(-2);}return d.getFullYear()+p(d.getMonth()+1)+p(d.getDate());}

/* ---- giao diện: thanh trên, ô Kho cục bộ ở Màn 05, nút xuất ---- */
function $(id){return document.getElementById(id);}
function nf(n){return String(n).replace(/\B(?=(\d{3})+(?!\d))/g,'.');}
function toast(h){var D=window.__dl;if(D&&D.toast){D.toast(h);}else if(window.console){console.log(h);}}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

function renderBanner(){
  var n=counts(),el=$('bn-note');if(!el){return;}
  var first=document.querySelector('.banner .bn-msgs span');if(first&&first!==el){first.textContent='Chế độ file · iHouzz · quét cộng đồng người Việt tại Hàn Quốc';}
  var total=n.sources+n.orgs+n.stats+n.signals;
  el.textContent=total
    ?'● Kho cục bộ trên trình duyệt này · '+nf(n.sources)+' nguồn · '+nf(n.orgs)+' đầu mối · '+nf(n.signals)+' tín hiệu · '+nf(n.stats)+' dòng thống kê'
    :'● Kho cục bộ trống — nạp file .jsonl của script ở Màn 05 để có số thật';
  if(!persistent&&!warned){warned=true;toast('<b>Trình duyệt không cho lưu lâu dài</b> (chế độ ẩn danh hoặc bị chặn): dữ liệu chỉ còn tới khi đóng tab. Hãy Sao lưu trước khi đóng.');}
}
function renderStorePanel(){
  var n=counts(),box=$('ldb-counts');if(!box){return;}
  box.innerHTML='<span class="label muted">Nguồn</span> <b>'+nf(n.sources)+'</b> · <span class="label muted">Đầu mối tổ chức</span> <b>'+nf(n.orgs)+'</b> · '
    +'<span class="label muted">Tín hiệu</span> <b>'+nf(n.signals)+'</b> · <span class="label muted">Thống kê</span> <b>'+nf(n.stats)+'</b>'
    +(persistent?'':' · <span class="st warn">không lưu được lâu dài</span>');
}
function buildStorePanel(){
  var after=$('s5-import');if(!after||$('ldb-panel')){return;}
  var p=document.createElement('div');p.className='panel';p.id='ldb-panel';p.setAttribute('data-real-zone','');
  p.innerHTML='<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap"><h2 class="sub">Kho dữ liệu cục bộ</h2><span class="label muted">Chế độ file · lưu trong trình duyệt này</span></div>'
    +'<div class="exp"><p>Trang này chạy <b>không có máy chủ</b>: mọi thứ bạn nạp hay thêm được giữ trong trình duyệt đang dùng, mở lại vẫn còn, nhưng <b>máy khác không thấy</b>.</p>'
    +'<p>Muốn chuyển sang máy khác hay gửi cho đồng nghiệp: bấm <b>Sao lưu kho</b> để tải file .json, rồi ở máy kia bấm <b>Khôi phục</b> và chọn file đó.</p></div>'
    +'<div class="help" id="ldb-counts" style="margin:4px 0 10px"></div>'
    +'<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">'
    +'<button class="btn line sm" type="button" id="ldb-export" data-real>Sao lưu kho (.json)</button>'
    +'<label class="btn line sm" style="cursor:pointer;margin:0">Khôi phục từ file<input type="file" id="ldb-import" accept=".json,application/json" style="display:none"></label>'
    +'<label class="help" style="display:flex;align-items:center;gap:6px;margin:0"><input type="checkbox" id="ldb-replace"> Thay thế toàn bộ kho (bỏ chọn = gộp thêm)</label>'
    +'<button class="btn line sm" type="button" id="ldb-clear" data-real style="margin-left:auto">Xóa kho</button>'
    +'</div>';
  after.parentNode.insertBefore(p,after.nextSibling);
  renderStorePanel();
}
function exportOrgsCSV(){
  var D=window.__dl,S=D&&D.S;if(!S){return;}
  var rows=S.orgs.filter(function(o){return o.verified==='Đã xác minh';});
  if(!rows.length){toast('Chưa có đầu mối nào ở trạng thái <b>Đã xác minh</b>. Chọn một dòng ở bảng rồi bấm "Đã xác minh" ở khung bên phải trước.');return;}
  var head=['Mã','Tên','Loại','Tỉnh/thành','Khu vực','Điện thoại chung','Email chung','Website','Facebook (trang tổ chức)','Zalo','YouTube','Địa chỉ','Nguồn công khai','Xác minh','Ngày quét'];
  var body=rows.map(function(o){return [o.code||o.id,o.name,o.type,o.province,o.subarea,o.phone,o.email,o.web,o.fb,o.zalo,o.yt,o.addr,o.src,o.verified,(o.createdAt||'').slice(0,10)];});
  download('ihouzz_dau_moi_da_xac_minh_'+today()+'.csv',csv([head].concat(body)),'text/csv');
  toast('<b>Đã xuất '+rows.length+' đầu mối đã xác minh</b> ra file CSV (mở được bằng Excel).');
}
function exportWeeklyReport(){
  var D=window.__dl,S=D&&D.S;if(!S){return;}
  if(!S.signals.length&&!S.orgs.length&&!S.stats.length){toast('Kho đang trống, chưa có gì để báo cáo. Nạp file ở Màn 05 trước.');return;}
  var weeks={};S.signals.forEach(function(s){if(s.tuan){weeks[s.tuan]=1;}});var wl=Object.keys(weeks).sort(),cur=wl[wl.length-1]||'',prev=wl.length>1?wl[wl.length-2]:'';
  function topics(w){var c={},n=0;S.signals.forEach(function(s){if(s.tuan===w){c[s.chu_de]=(c[s.chu_de]||0)+1;n++;}});return {c:c,n:n};}
  var t=topics(cur),pv=prev?topics(prev):null;
  var lines=['# Báo cáo tuần · Cộng đồng người Việt tại Hàn Quốc','','Xuất từ kho cục bộ ngày '+new Date().toLocaleDateString('vi-VN')+'. Số liệu từ nguồn công khai, tín hiệu đã ẩn danh; không có dữ liệu cá nhân.',''];
  lines.push('## Tín hiệu nhu cầu · tuần '+(cur||'—')+' ('+t.n+' bài'+(pv?', tuần trước '+pv.n:'')+')','');
  Object.keys(t.c).sort(function(a,b){return t.c[b]-t.c[a];}).forEach(function(k){var pct=t.n?Math.round(100*t.c[k]/t.n):0,d='';if(pv&&pv.n){var df=pct-Math.round(100*(pv.c[k]||0)/pv.n);d=df>0?' (▲'+df+' điểm)':(df<0?' (▼'+(-df)+' điểm)':'');}lines.push('- '+k+': '+t.c[k]+' bài · '+pct+'%'+d);});
  var need=S.signals.filter(function(s){return s.tuan===cur&&s.nhu_cau_ro==='Có';}).length;
  lines.push('','Bài nói rõ nhu cầu: '+need+'/'+t.n+'.','');
  var vf={};S.orgs.forEach(function(o){var k=o.verified||'Chờ xác minh';vf[k]=(vf[k]||0)+1;});
  lines.push('## Đầu mối tổ chức: '+S.orgs.length,'');Object.keys(vf).forEach(function(k){lines.push('- '+k+': '+vf[k]);});
  var st=S.stats.filter(function(x){return x.metric==='nguoi_viet_theo_tinh'&&x.area==='Toàn quốc';}).sort(function(a,b){return a.period<b.period?1:-1;})[0];
  if(st){lines.push('','## Thống kê chính thức','','- Người Việt tại Hàn (toàn quốc, kỳ '+st.period+'): '+nf(st.value)+(st.src?' · nguồn: '+st.src:''));}
  lines.push('','## Nguồn đang dùng: '+S.sources.length,'');
  S.sources.forEach(function(s){lines.push('- '+(s.name||s.id)+(s.schedule?' · '+s.schedule:'')+(s.lastLoad?' · nạp lần cuối '+String(s.lastLoad).slice(0,10):''));});
  download('ihouzz_bao_cao_tuan_'+(cur||today())+'.md',lines.join('\n'),'text/markdown');
  toast('<b>Đã xuất báo cáo tuần</b> (.md) từ kho cục bộ.');
}
function afterRender(){
  var ex=$('s2-export');if(ex){ex.style.display='';ex.setAttribute('data-real','1');ex.title='Tải CSV các đầu mối đang ở trạng thái Đã xác minh';}
  var s1=$('s1-export');if(s1){s1.setAttribute('data-real','1');}
  renderBanner();renderStorePanel();
}
function wireUI(){
  /* Nút "Reset giao diện demo" giữ nguyên: khi kho trống trang vẫn là bản thử, Reset chạy như cũ
     (xem doReset trong ui.js); khi kho có dữ liệu thật, nút chỉ báo và chỉ sang "Xóa kho". */
  buildStorePanel();
  var D=window.__dl;
  if(D&&D.renderAll&&!D.renderAll.__ldb){var orig=D.renderAll;D.renderAll=function(){orig();afterRender();};D.renderAll.__ldb=true;}
  afterRender();
  document.addEventListener('click',function(e){
    var b=e.target&&e.target.closest?e.target.closest('button'):null;if(!b){return;}
    if(b.id==='s2-export'){exportOrgsCSV();return;}
    if(b.id==='s1-export'){exportWeeklyReport();return;}
    if(b.id==='ldb-export'){var n=counts();download('ihouzz_kho_'+today()+'.json',exportJSON(),'application/json');toast('<b>Đã sao lưu kho</b> ('+nf(n.sources+n.orgs+n.stats+n.signals)+' bản ghi). Giữ file này ở nơi nội bộ, không gửi ra ngoài.');return;}
    if(b.id==='ldb-clear'){if(window.confirm('Xóa toàn bộ kho cục bộ trên trình duyệt này? Hãy Sao lưu trước nếu cần giữ. Không hoàn tác được.')){clearAll();toast('Đã xóa kho cục bộ. Các màn quay về dữ liệu mẫu.');}return;}
  });
  document.addEventListener('change',function(e){
    var inp=e.target;if(!inp||inp.id!=='ldb-import'||!inp.files||!inp.files[0]){return;}
    var f=inp.files[0],rd=new FileReader();
    rd.onload=function(){try{var replace=!!($('ldb-replace')&&$('ldb-replace').checked);var added=importJSON(String(rd.result||''),replace);var n=counts();toast('<b>Đã khôi phục kho</b> từ '+esc(f.name)+(replace?' (thay thế toàn bộ)':' (gộp thêm '+nf(added)+' bản ghi mới)')+'. Hiện có '+nf(n.sources+n.orgs+n.stats+n.signals)+' bản ghi.');}catch(er){toast('<b>Không khôi phục được:</b> '+esc(er.message||er));}inp.value='';};
    rd.onerror=function(){toast('Không đọc được file.');inp.value='';};
    rd.readAsText(f,'utf-8');
  });
}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',wireUI);}else{wireUI();}
})();
