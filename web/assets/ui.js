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
  var currentS2Row=null,s2ShowAll=false;
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
    var sel=tb.querySelector('tr.sel')||rows[0];if(sel){currentS2Row=sel;renderChannels(sel,false);}
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
    function close(){if(btn.dataset.open==='1'){sp.remove();btn.textContent='hiện';btn.dataset.open='';}}
    btn._close=close;setTimeout(close,60000);
  }
  document.addEventListener('click',function(e){
    var nv=e.target.closest('[data-s]');if(nv){show(nv.dataset.s);return;}
    var rv=e.target.closest('.reveal');if(rv){if(rv.dataset.open==='1'){if(rv._close){rv._close();}}else{reveal(rv);}return;}
    if(e.target.closest('#s2-filters')&&e.target.closest('button')){filter2();return;}
    var row=e.target.closest('#s2-rows tr');if(row){pick2(row);return;}
    var pl=e.target.closest('#s6 a[href="#"]');if(pl){e.preventDefault();toast('Mở thông báo quyền riêng tư đầy đủ (demo).');return;}
    var xc=e.target.closest('[data-close="addsrc"]');if(xc){hideAdd();return;}
    var b=e.target.closest('button');if(!b){return;}
    if(b.dataset.s||b.getAttribute('type')==='submit'||b.disabled){return;}
    if(b.dataset.act==='s3log'){var l=document.getElementById('s3-log');if(l){l.scrollIntoView({behavior:'smooth',block:'center'});}toast('Cuộn tới nhật ký truy cập.');return;}
    if(b.dataset.act==='confirmlabel'){b.textContent='✓ Đã xác nhận';b.disabled=true;b.parentNode.querySelectorAll('button').forEach(function(x){if(x!==b){x.disabled=true;}});toast('<b>Đã xác nhận nhãn</b> cho bài này (demo).');return;}
    if(b.dataset.act==='addsrc'){showAdd();return;}
    if(b.classList.contains('preveal')){var pvv=b.parentNode.querySelector('.pv');var fl=b.getAttribute('data-full');if(pvv){pvv.textContent=fl;}var cpb=document.createElement('button');cpb.type='button';cpb.className='btn line xs pcopy';cpb.setAttribute('data-v',fl);cpb.textContent='Chép';b.replaceWith(cpb);toast('<b>Đã hiện</b> — thao tác này được ghi nhật ký (demo).');return;}
    if(b.classList.contains('pcopy')){var cv=b.getAttribute('data-v');try{if(navigator.clipboard){navigator.clipboard.writeText(cv);}}catch(e){}toast('<b>Đã sao chép</b> — '+cv);return;}
    if(b.id==='s2-ch-toggle'){s2ShowAll=!s2ShowAll;b.textContent=s2ShowAll?'Thu gọn':'Hiện tất cả';renderChannels(currentS2Row,s2ShowAll);return;}
    if(b.hasAttribute('data-real')||b.closest('[data-real-zone]')){return;}
    var label=b.textContent.trim().replace(/\s+/g,' ');
    toast('<b>Demo:</b> "'+label+'" — bản thật sẽ thực hiện thao tác này.');
  });
  var form=document.querySelector('#s6 form');
  if(form){form.addEventListener('submit',function(){toast('<b>Đã gửi khảo sát (demo)</b> — bản thật lưu vào hệ thống kèm thời điểm đồng ý.');});}
  var af=document.getElementById('addsrc-form');
  if(af){af.addEventListener('submit',function(e){
    e.preventDefault();if(window.__realdb){return;}
    var fd=new FormData(af);var ten=(fd.get('ten')||'').trim();if(!ten){return;}
    var tb=document.getElementById('s5-rows');if(!tb){return;}
    var tr=document.createElement('tr');
    tr.innerHTML='<td class="id">'+esch(fd.get('lop'))+'</td><td class="strong">'+esch(ten)+'</td><td>'+esch(fd.get('cach'))+'</td><td>'+esch(fd.get('lich'))+'</td><td class="num">0</td><td>'+esch(fd.get('daumoi'))+'</td><td><span class="st info">Mới thêm</span></td>';
    tb.appendChild(tr);updSrcCount();hideAdd();
    toast('<b>Đã thêm nguồn</b> "'+esch(ten)+'" vào bảng (bản thử) — trạng thái Mới thêm.');
  });}
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&addM&&addM.style.display!=='none'){hideAdd();}});
  var colmenu=document.getElementById('s2-colmenu');
  if(colmenu){colmenu.addEventListener('change',function(e){var cb=e.target;if(cb&&cb.dataset&&cb.dataset.col){var disp=cb.checked?'table-cell':'none';document.querySelectorAll('.cc-'+cb.dataset.col).forEach(function(el){el.style.display=disp;});}});}
  initS2();
  renderVcheck('Đã xác minh','A');
  window.__ihz={toast:toast,esch:esch,show:show,s2mask:s2mask,s2Badges:s2Badges,pick2:pick2,S2CH:S2CH,renderChannels:renderChannels};
})();
