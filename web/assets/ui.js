(function(){
  var screens=document.querySelectorAll('.screen');
  var nav=document.querySelectorAll('.navlist button');
  function show(id){
    screens.forEach(function(s){s.classList.toggle('on',s.id===id);});
    nav.forEach(function(b){b.classList.toggle('on',b.dataset.s===id);});
    try{window.scrollTo({top:0,behavior:'smooth'});}catch(e){window.scrollTo(0,0);}
  }
  var tw=document.getElementById('toasts');
  function toast(msg){
    if(!tw){return;}
    var el=document.createElement('div');el.className='toast';el.innerHTML=msg;tw.appendChild(el);
    requestAnimationFrame(function(){el.classList.add('show');});
    setTimeout(function(){el.classList.remove('show');setTimeout(function(){el.remove();},250);},3400);
  }
  var addM=document.getElementById('addsrc-modal');
  function esch(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function updSrcCount(){
    var tb=document.getElementById('s5-rows');if(!tb){return;}
    var n=tb.querySelectorAll('tr').length;
    var h=document.getElementById('src-head');if(h){h.textContent='Nguồn & lịch · '+n+' nguồn, 3 nhóm';}
    var t=document.getElementById('src-total');if(t){t.textContent='/ '+n;}
    var c=document.getElementById('src-collect');if(c){c.textContent=n+' nguồn · 412 bài mới';}
  }
  function showAdd(){if(!addM){return;}addM.style.display='flex';var r=!!window.__realdb;var a1=document.getElementById('addsrc-form'),a2=document.getElementById('addsrc-form2');if(a1){a1.style.display=r?'none':'grid';}if(a2){a2.style.display=r?'grid':'none';}var tt=document.getElementById('addsrc-title');if(tt){tt.textContent=r?'Thêm nguồn thật':'Thêm một nguồn';}var i=addM.querySelector(r?'input[name=ten2]':'input[name=ten]');if(i){setTimeout(function(){try{i.focus();}catch(e){}},30);}}
  function hideAdd(){if(!addM){return;}addM.style.display='none';var f=document.getElementById('addsrc-form');if(f){f.reset();}var f2=document.getElementById('addsrc-form2');if(f2){f2.reset();var bl=document.getElementById('as2-block');if(bl){bl.style.display='none';}}}
  function filter2(){
    var box=document.getElementById('s2-filters');if(!box){return;}
    function sv(f){var el=box.querySelector('[data-f="'+f+'"]');return el?el.value:'';}
    var search=box.querySelector('input');
    var q=((search&&search.value)||'').trim().toLowerCase();var shown=0;
    document.querySelectorAll('#s2-rows tr').forEach(function(r){
      var txt=r.textContent.toLowerCase();var html=r.innerHTML;var ok=true;
      var loai=sv('loai');if(loai.indexOf('Tất cả')<0){var w=loai.toLowerCase().split(/[ ,]/)[0];if(txt.indexOf(w)<0){ok=false;}}
      var kv=sv('kv');if(kv&&kv.indexOf('Tất cả')<0){if(txt.indexOf(kv.toLowerCase())<0){ok=false;}}
      var kvn=sv('kvn');if(kvn&&kvn.indexOf('Tất cả')<0){if(txt.indexOf(kvn.toLowerCase().split(' (')[0])<0){ok=false;}}
      var muc=sv('muc');if(muc.indexOf('A và B')<0){var mk=muc.trim().charAt(0).toUpperCase();if(html.indexOf('>'+mk+'</span>')<0){ok=false;}}
      var xm=sv('xm');if(xm.indexOf('Tất cả')<0){if(txt.indexOf(xm.toLowerCase())<0){ok=false;}}
      if(q&&txt.indexOf(q)<0){ok=false;}
      r.style.display=ok?'':'none';if(ok){shown++;}
    });
    var c=document.getElementById('s2-count');var tot=document.querySelectorAll('#s2-rows tr').length;if(c){c.textContent='Hiện '+shown+' trong '+tot+' · đã lọc theo lựa chọn';}
    toast('<b>Đã lọc</b> — '+shown+' kết quả khớp'+(window.__s2real?'.':' (dữ liệu mẫu).'));
  }
  var currentS2Row=null,s2ShowAll=false,s2SeedRow=null;
  var S2CH=[['dt','Số điện thoại'],['email','Email'],['web','Website'],['fb','Facebook'],['zalo','Zalo'],['yt','YouTube/TikTok'],['addr','Địa chỉ'],['src','Link nguồn gốc']];
  var S2BADGE={dt:'ĐT',email:'Email',web:'Web',fb:'FB',zalo:'Zalo',yt:'YT',addr:'Địa chỉ'};
  function s2esc(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function s2Badges(r){var out=[];Object.keys(S2BADGE).forEach(function(k){if(r.getAttribute('data-'+k)){out.push('<span class="kb">'+S2BADGE[k]+'</span>');}});return out.join('')||'<span class="help">—</span>';}
  function s2mask(val){
    if(!val){return '';}
    if(val.indexOf('•')>=0){return val;}
    if(val.indexOf('@')>=0){return val.charAt(0)+'••••@••••';}
    if(/^[+\d][\d\s\-()]*$/.test(val.trim())){var out='';for(var i=0;i<val.length;i++){var ch=val[i];out+=(i<6||ch===' '||ch==='+'||ch==='-'||ch==='('||ch===')')?ch:'•';}return out;}
    return '••••••••';
  }
  function renderChannels(r,showAll){
    var box=document.getElementById('s2-d-channels');if(!box||!r){return;}
    box.innerHTML='';
    S2CH.forEach(function(c){
      var k=c[0],val=r.getAttribute('data-'+k)||'',full=r.getAttribute('data-'+k+'-full')||val;
      if(!val&&!showAll){return;}
      var v;
      if(!val){v='<span class="help">— chưa có</span>';}
      else if(k==='src'){v='<span>'+s2esc(val)+'</span> <button type="button" class="btn line xs pcopy" data-v="'+s2esc(val)+'">Chép</button>';}
      else {v='<span class="pv">'+s2esc(s2mask(val))+'</span> <button type="button" class="btn line xs preveal" data-full="'+s2esc(full)+'">Hiện</button>';}
      var row=document.createElement('div');row.className='chrow';
      row.innerHTML='<span class="chk">'+c[1]+'</span><span class="chval">'+v+'</span>';
      box.appendChild(row);
    });
  }
  function initS2(){
    var tb=document.getElementById('s2-rows');if(!tb){return;}
    var rows=tb.querySelectorAll('tr');
    rows.forEach(function(r){var cell=r.querySelector('.s2-kenh');if(cell){cell.innerHTML=s2Badges(r);}});
    var table=tb.closest('table'),htr=table.querySelector('thead tr');
    S2CH.forEach(function(c){var th=document.createElement('th');th.className='cc cc-'+c[0];th.textContent=c[1];htr.appendChild(th);});
    rows.forEach(function(r){S2CH.forEach(function(c){var td=document.createElement('td');td.className='cc cc-'+c[0];var vv=r.getAttribute('data-'+c[0])||'';td.textContent=vv?(c[0]==='src'?vv:s2mask(vv)):'—';r.appendChild(td);});});
    var sel=tb.querySelector('tr.sel')||rows[0];if(sel){currentS2Row=sel;s2SeedRow=sel;renderChannels(sel,false);}
  }
  function pick2(r){
    var td=r.querySelectorAll('td');if(td.length<8){return;}
    document.querySelectorAll('#s2-rows tr').forEach(function(x){x.classList.remove('sel');});
    r.classList.add('sel');
    function g(i){return td[i]?td[i].textContent.trim():'';}
    function set(id,v){var e=document.getElementById(id);if(e){e.textContent=v;}}
    set('s2-d-code',g(0)+' · mức '+g(6));set('s2-d-name',g(1));set('s2-d-loai',g(2));set('s2-d-area',g(3));set('s2-d-nguon',g(5));currentS2Row=r;renderChannels(r,s2ShowAll);
    var stt=document.getElementById('s2-d-status');if(stt){stt.outerHTML=td[7].innerHTML.replace('<span class="st','<span id="s2-d-status" class="st');}
    renderVcheck(g(7),g(6));
  }
  function renderVcheck(status,level){
    var el=document.getElementById('s2-vcheck');if(!el){return;}
    var isB=(level||'').toUpperCase().indexOf('B')>=0;
    var crit=['Có thật, đúng phân loại','Liên hệ được (gọi · email · web còn sống)',isB?'Có bằng chứng tự công khai nhận liên hệ':'Khớp từ 2 nguồn trở lên (hoặc nguồn chính thức)','Không trùng — đã gộp dòng'];
    var st=(status||'').toLowerCase();var marks;
    if(st.indexOf('đã xác minh')>=0){marks=['ok','ok','ok','ok'];}
    else if(st.indexOf('không liên lạc')>=0){marks=['ok','bad','ok','ok'];}
    else {marks=['ok','wait','wait','ok'];}
    var sym={ok:'✓',wait:'⋯',bad:'×'};el.innerHTML='';
    crit.forEach(function(c,i){var li=document.createElement('li');li.className=marks[i];li.innerHTML='<span class="mk">'+sym[marks[i]]+'</span><span>'+c+'</span>';el.appendChild(li);});
  }
  function reveal(btn){
    if(btn.dataset.open==='1'){return;}
    btn.dataset.open='1';
    var sp=document.createElement('span');sp.textContent=(btn.getAttribute('data-full')||'')+' ';
    btn.parentNode.insertBefore(sp,btn);btn.textContent='ẩn';
    var log=document.getElementById('s3-log');
    if(log){var d=new Date();var hh=('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2);var li=document.createElement('li');li.innerHTML='<i>'+hh+'</i><i>AI Team · Phương</i><span>Mở số '+(btn.getAttribute('data-id')||'')+' · tự ẩn sau 60 giây</span>';log.insertBefore(li,log.firstChild);}
    toast('<b>Đã mở số 60 giây</b> — một dòng nhật ký vừa được ghi.');
    logAction('reveal','Hiện số liên hệ '+(btn.getAttribute('data-id')||'')+' ở Màn 03 · Cá nhân đồng ý');
    function close(){if(btn.dataset.open==='1'){sp.remove();btn.textContent='hiện';btn.dataset.open='';}}
    btn._close=close;setTimeout(close,60000);
  }
  document.addEventListener('click',function(e){
    var nv=e.target.closest('[data-s]');if(nv){show(nv.dataset.s);if(nv.dataset.s==='s8'){renderS8();}return;}
    var rb=e.target.closest('#bn-reset');if(rb){doReset();return;}
    var s8d=e.target.closest('[data-s8del]');if(s8d){var di=parseInt(s8d.getAttribute('data-s8del'),10);var sarr=loadSaved();if(!isNaN(di)&&sarr[di]){sarr.splice(di,1);saveSaved(sarr);renderS8();toast('Đã xoá 1 kết quả đã lưu.');}return;}
    var s8a=e.target.closest('[data-s8delall]');if(s8a){if(!loadSaved().length){toast('Chưa có kết quả nào để xoá.');return;}if(window.confirm('Xoá toàn bộ kết quả đã lưu? Không hoàn tác được.')){saveSaved([]);renderS8();toast('Đã xoá toàn bộ kết quả đã lưu.');}return;}
    var rv=e.target.closest('.reveal');if(rv){if(rv.dataset.open==='1'){if(rv._close){rv._close();}}else{reveal(rv);}return;}
    if(e.target.closest('#s2-filters')&&e.target.closest('button')){filter2();return;}
    var row=e.target.closest('#s2-rows tr');if(row){pick2(row);return;}
    var pl=e.target.closest('#s6 a[href="#"]');if(pl){e.preventDefault();toast('Mở thông báo quyền riêng tư đầy đủ (demo).');return;}
    var xc=e.target.closest('[data-close="addsrc"]');if(xc){hideAdd();return;}
    var b=e.target.closest('button');if(!b){return;}
    if(b.dataset.s||b.getAttribute('type')==='submit'||b.disabled){return;}
    if(b.dataset.act==='s3log'){var l=document.getElementById('s3-log');if(l){l.scrollIntoView({behavior:'smooth',block:'center'});}toast('Cuộn tới nhật ký truy cập.');return;}
    if(b.dataset.act==='confirmlabel'){b.textContent='✓ Đã xác nhận';b.disabled=true;b.parentNode.querySelectorAll('button').forEach(function(x){if(x!==b){x.disabled=true;}});toast('<b>Đã xác nhận nhãn</b> cho bài này (demo).');logAction('confirmlabel','Xác nhận nhãn 1 bài ở Màn 04 · Tín hiệu nhu cầu');return;}
    if(b.dataset.act==='addsrc'){showAdd();return;}
    if(b.classList.contains('preveal')){var pvv=b.parentNode.querySelector('.pv');var fl=b.getAttribute('data-full');if(pvv){pvv.textContent=fl;}var cpb=document.createElement('button');cpb.type='button';cpb.className='btn line xs pcopy';cpb.setAttribute('data-v',fl);cpb.textContent='Chép';b.replaceWith(cpb);toast('<b>Đã hiện</b> — thao tác này được ghi nhật ký (demo).');return;}
    if(b.classList.contains('pcopy')){var cv=b.getAttribute('data-v');try{if(navigator.clipboard){navigator.clipboard.writeText(cv);}}catch(e){}toast('<b>Đã sao chép</b> — '+cv);return;}
    if(b.id==='s2-ch-toggle'){s2ShowAll=!s2ShowAll;b.textContent=s2ShowAll?'Thu gọn':'Hiện tất cả';renderChannels(currentS2Row,s2ShowAll);return;}
    if(b.hasAttribute('data-real')||b.closest('[data-real-zone]')){return;}
    var label=b.textContent.trim().replace(/\s+/g,' ');
    toast('<b>Demo:</b> "'+label+'" — bản thật sẽ thực hiện thao tác này.');
  });
  var form=document.querySelector('#s6 form');
  if(form){form.addEventListener('submit',function(){toast('<b>Đã gửi khảo sát (demo)</b> — bản thật lưu vào hệ thống kèm thời điểm đồng ý.');logAction('survey','Gửi khảo sát demo ở Màn 06 · Biểu mẫu khảo sát');});}
  var af=document.getElementById('addsrc-form');
  if(af){af.addEventListener('submit',function(e){
    e.preventDefault();if(window.__realdb){return;}
    var fd=new FormData(af);var ten=(fd.get('ten')||'').trim();if(!ten){return;}
    var tb=document.getElementById('s5-rows');if(!tb){return;}
    var tr=document.createElement('tr');
    tr.innerHTML='<td class="id">'+esch(fd.get('lop'))+'</td><td class="strong">'+esch(ten)+'</td><td>'+esch(fd.get('cach'))+'</td><td>'+esch(fd.get('lich'))+'</td><td class="num">0</td><td>'+esch(fd.get('daumoi'))+'</td><td><span class="st info">Mới thêm</span></td>';
    tb.appendChild(tr);updSrcCount();hideAdd();
    toast('<b>Đã thêm nguồn</b> "'+esch(ten)+'" vào bảng (bản thử) — trạng thái Mới thêm.');
    logAction('addsrc','Thêm nguồn demo "'+ten+'" ở Màn 05 · Nguồn & lịch quét');
  });}
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&addM&&addM.style.display!=='none'){hideAdd();}});
  var colmenu=document.getElementById('s2-colmenu');
  if(colmenu){colmenu.addEventListener('change',function(e){var cb=e.target;if(cb&&cb.dataset&&cb.dataset.col){var disp=cb.checked?'table-cell':'none';document.querySelectorAll('.cc-'+cb.dataset.col).forEach(function(el){el.style.display=disp;});}});}
  /* ===== Phiên demo: ghi log thao tác + nút Reset + màn "08 · Kết quả đã lưu" ===== */
  var LOGKEY='ihz_demo_saved_results_v1';
  var SESSLOG=[];
  function logAction(kind,label){SESSLOG.push({t:Date.now(),kind:kind,label:label});}
  function loadSaved(){try{var raw=localStorage.getItem(LOGKEY);var arr=raw?JSON.parse(raw):[];return Array.isArray(arr)?arr:[];}catch(e){return [];}}
  function saveSaved(arr){try{localStorage.setItem(LOGKEY,JSON.stringify(arr));return true;}catch(e){return false;}}
  function fmtSaved(ts){var d=new Date(ts);function p(n){return ('0'+n).slice(-2);}return p(d.getDate())+'.'+p(d.getMonth()+1)+'.'+d.getFullYear()+' '+p(d.getHours())+':'+p(d.getMinutes());}
  function groupCounts(log){var c={addsrc:0,confirmlabel:0,reveal:0,survey:0};log.forEach(function(a){if(c[a.kind]!=null){c[a.kind]++;}});return c;}
  function buildSummary(c,total){
    var parts=[];
    if(c.addsrc){parts.push(c.addsrc+' nguồn mới');}
    if(c.confirmlabel){parts.push(c.confirmlabel+' nhãn đã xác nhận');}
    if(c.reveal){parts.push(c.reveal+' lượt hiện số');}
    if(c.survey){parts.push(c.survey+' lượt gửi khảo sát');}
    if(!parts.length&&total){parts.push(total+' thao tác khác');}
    return parts.join(' · ');
  }
  function resetS5(){
    var tb=document.getElementById('s5-rows');if(!tb){return;}
    tb.querySelectorAll('tr').forEach(function(tr){if(!tr.hasAttribute('data-seed')){tr.remove();}});
    updSrcCount();
  }
  function resetS4(){
    document.querySelectorAll('[data-act="confirmlabel"]').forEach(function(b){
      b.textContent='Đúng nhãn';b.disabled=false;
      if(b.parentNode){b.parentNode.querySelectorAll('button').forEach(function(x){x.disabled=false;});}
    });
  }
  function resetS3(){
    document.querySelectorAll('.reveal').forEach(function(btn){
      if(btn.dataset.open==='1'){if(btn._close){btn._close();}else{btn.dataset.open='';btn.textContent='hiện';}}
    });
    var log=document.getElementById('s3-log');
    if(log){log.querySelectorAll('li').forEach(function(li){if(!li.hasAttribute('data-seed')){li.remove();}});}
  }
  function resetS2(){
    var box=document.getElementById('s2-filters');
    if(box){box.querySelectorAll('select').forEach(function(s){s.selectedIndex=0;});var inp=box.querySelector('input');if(inp){inp.value='';}}
    document.querySelectorAll('#s2-rows tr').forEach(function(r){r.style.display='';});
    var tot=document.querySelectorAll('#s2-rows tr').length,c=document.getElementById('s2-count');
    if(c){c.textContent='Hiện '+tot+' trong '+tot+' · số điện thoại che một phần trên màn hình danh sách';}
    document.querySelectorAll('#s2-colmenu input[type=checkbox]').forEach(function(cb){
      if(cb.dataset&&cb.dataset.col){document.querySelectorAll('.cc-'+cb.dataset.col).forEach(function(el){el.style.display='none';});}
      cb.checked=false;
    });
    s2ShowAll=false;
    var toggle=document.getElementById('s2-ch-toggle');if(toggle){toggle.textContent='Hiện tất cả';}
    if(s2SeedRow){pick2(s2SeedRow);}
  }
  function resetS6(){var f=document.querySelector('#s6 form');if(f){try{f.reset();}catch(e){}}}
  function renderS8(){
    var list=document.getElementById('s8-list'),empty=document.getElementById('s8-empty');if(!list){return;}
    var arr=loadSaved();
    if(empty){empty.style.display=arr.length?'none':'';}
    list.innerHTML=arr.slice().reverse().map(function(item){
      var idx=arr.indexOf(item);
      var acts=(item.actions||[]).map(function(a){return '<span class="help">· '+esch(a)+'</span>';}).join('');
      return '<div class="panel" style="gap:10px">'
        +'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">'
        +'<h2 class="sub" style="font-size:16px">Lưu lúc '+fmtSaved(item.savedAt)+'</h2>'
        +'<button class="btn line sm" type="button" data-s8del="'+idx+'">Xoá</button>'
        +'</div>'
        +'<span class="help">'+esch(item.summary||'')+'</span>'
        +(acts?'<div style="display:flex;flex-direction:column;gap:4px">'+acts+'</div>':'')
        +'</div>';
    }).join('');
  }
  function doReset(){
    /* Reset luôn làm việc thấy rõ: đưa toàn bộ giao diện về trạng thái ban đầu và báo kết quả.
       - Có thao tác demo trong phiên -> lưu tóm tắt vào Màn 08 trước (như bản V19).
       - Chế độ file (localdb.js) và kho cục bộ đang có dữ liệu -> hỏi: OK = xóa kho về dữ liệu mẫu,
         Cancel = giữ dữ liệu, chỉ làm mới giao diện.
       - Trên claude.ai (kho thật của nền tảng) thì không đụng dữ liệu, chỉ làm mới giao diện. */
    var ldb=window.__localdb,c=(ldb&&ldb.counts)?ldb.counts():null;
    var nStore=c?(c.sources+c.orgs+c.stats+c.signals):0;
    var nAct=SESSLOG.length,notes=[];
    if(nAct){
      var counts=groupCounts(SESSLOG),summary=buildSummary(counts,nAct);
      if(window.confirm('Lưu '+nAct+' thao tác vừa làm ('+summary+') vào "08 · Kết quả đã lưu" trước khi đưa giao diện về ban đầu?\n\nOK = lưu rồi reset · Cancel = reset, không lưu')){
        var arr=loadSaved();
        arr.push({savedAt:Date.now(),summary:summary,actions:SESSLOG.map(function(a){return a.label;})});
        if(arr.length>50){arr=arr.slice(arr.length-50);}
        notes.push(saveSaved(arr)?'đã lưu '+nAct+' thao tác vào Màn 08':'không lưu được vào trình duyệt (bộ nhớ đầy hoặc bị chặn)');
      }
    }
    if(nStore&&ldb&&ldb.clear){
      if(window.confirm('Kho cục bộ đang có '+nStore+' bản ghi (nguồn, đầu mối, tín hiệu, thống kê).\n\nOK = XÓA kho, đưa trang về dữ liệu mẫu · Cancel = giữ dữ liệu, chỉ làm mới giao diện\n(Muốn giữ lại thì bấm Cancel, vào Màn 05 "Sao lưu kho" trước.)')){
        ldb.clear();notes.push('đã xóa kho cục bộ ('+nStore+' bản ghi)');
      }else{notes.push('kho cục bộ giữ nguyên');}
    }else if(window.__realdb&&!c){
      notes.push('kho dữ liệu của trang giữ nguyên');
    }
    resetS5();resetS4();resetS3();resetS2();resetS6();
    SESSLOG=[];
    renderS8();
    show('s0');
    try{window.scrollTo({top:0,behavior:'smooth'});}catch(e){}
    toast('<b>Đã đưa giao diện về trạng thái ban đầu</b>'+(notes.length?' · '+notes.join(' · '):'')+'.');
  }

  initS2();
  renderVcheck('Đã xác minh','A');
  renderS8();
  window.__ihz={toast:toast,esch:esch,show:show,s2mask:s2mask,s2Badges:s2Badges,pick2:pick2,S2CH:S2CH,renderChannels:renderChannels};
})();
