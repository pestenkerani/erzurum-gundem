const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fold = s => String(s).toLocaleLowerCase('tr-TR').replace(/[çğıöşü]/g, c=>({'ç':'c','ğ':'g','ı':'i','ö':'o','ş':'s','ü':'u'}[c]));
let state = null, view = 'all', editing = null, polling = null;
const date = s => new Date(s).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
function toast(message){ $('toast').textContent=message; $('toast').style.display='block'; setTimeout(()=>$('toast').style.display='none',3500); }
const storageKey = 'erzurum-v1:' + location.pathname.replace(/index\.html$/, '');
let archive = null;
function localData(){
  try { return JSON.parse(localStorage.getItem(storageKey) || '{}'); }
  catch { return {}; }
}
async function post(path, body){
  if(path === '/api/refresh') return {ok:true};
  const local = localData();
  if(path === '/api/watch') local.watch = body.words;
  if(path === '/api/article') {
    local.articles ||= {};
    local.articles[body.id] = {...local.articles[body.id], ...body};
  }
  try { localStorage.setItem(storageKey, JSON.stringify(local)); }
  catch { throw Error('Tarayıcı kayıt alanına yazılamadı. Gizli mod veya depolama sınırını kontrol edin.'); }
  return {ok:true};
}
function download(text, name, type){
  const url = URL.createObjectURL(new Blob([text], {type}));
  const a = document.createElement('a'); a.href=url; a.download=name; a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 3000);
}
function exportCsv(){
  const safe = value => { let s=String(value??''); if(/^[\s]*[=+@-]/.test(s))s="'"+s; return '"'+s.replace(/"/g,'""')+'"'; };
  const rows = [['Başlık','Kaynak','Yayın zamanı (Türkiye)','Konu','İlçe','Bağlantı','Not'], ...state.articles.map(a=>[a.title,a.source,date(a.published),a.category,a.districts.join(', '),a.url,a.note])];
  download('\ufeff'+rows.map(r=>r.map(safe).join(',')).join('\r\n'), 'erzurum-haberler.csv', 'text/csv;charset=utf-8');
}
function exportBrief(){
  const local=localData();
  const rows=archive.articles.filter(a=>Date.parse(a.published)>=Date.now()-86400000 && Date.parse(a.published)<=Date.now()+600000);
  const lines=['# Erzurum Gündem — Günlük Brifing', '', 'Hazırlanma: '+date(new Date()), 'Son başarılı tarama: '+(archive.last_success?date(archive.last_success):'Henüz yok'), '', 'Son 24 saatte yayımlanan başlıklar. Tam metin özeti veya doğruluk teyidi değildir.', ''];
  if(!rows.length)lines.push('Bu dönemde kayıt yok; kaynakların tarama durumunu kontrol edin.');
  for(const category of archive.categories){
    const group=rows.filter(a=>a.category===category);if(!group.length)continue;
    lines.push('## '+category,'');
    for(const a of group){lines.push('- '+a.title+' — '+a.source+' · '+date(a.published), '  Kaynak: '+a.url);const note=local.articles?.[a.id]?.note;if(note)lines.push('  Danışman notu: '+note.replace(/\n/g,' '));}
    lines.push('');
  }
  download(lines.join('\n'),'erzurum-gunluk-brifing.md','text/markdown;charset=utf-8');
}
function matches(article){return state.watch.filter(w=>fold(article.title).includes(fold(w)));}
async function load(){
  try{
    const response=await fetch('./news.json', {cache:'no-store'}); if(!response.ok)throw Error('Haber dosyasına erişilemiyor');
    const incoming=await response.json();
    if(!Array.isArray(incoming.articles)||!Array.isArray(incoming.categories)||!Array.isArray(incoming.districts))throw Error('Geçersiz haber dosyası');
    archive=incoming;
    const local=localData(), cutoff=Date.now()-Number($('period').value)*3600000;
    const next={...archive, busy:false, watch:Array.isArray(local.watch)?local.watch:['ihale','yatırım','çiftçi','su kesintisi'], articles:archive.articles.filter(a=>Date.parse(a.published)>=cutoff&&Date.parse(a.published)<=Date.now()+600000&&/^https?:\/\//.test(a.url)).map(a=>({...a, saved:Boolean(local.articles?.[a.id]?.saved),note:String(local.articles?.[a.id]?.note||'')}))};
    const first=!state;state=next;
    if(first){for(const d of state.districts)$('district').add(new Option(d,d));for(const c of state.categories)$('category').add(new Option(c,c));$('watch-input').value=state.watch.join(', ');}
    $('total').textContent=state.articles.length;$('nav-count').textContent=state.articles.length;$('source-count').textContent=new Set(state.articles.map(a=>a.source)).size;$('watch-count').textContent=state.articles.filter(a=>matches(a).length).length;
    const run=state.last_run;$('last-time').textContent=run?new Date(run.at).toLocaleTimeString('tr-TR',{timeZone:'Europe/Istanbul',hour:'2-digit',minute:'2-digit'}):'Henüz yok';
    $('health').textContent=run?date(run.at)+' · '+run.success+'/'+run.total+' akış':'İlk tarama bekleniyor';
    $('refresh').disabled=state.busy;$('refresh').textContent=state.busy?'↻ Taranıyor…':'↻ Listeyi yenile';
    $('notice').classList.toggle('error',Boolean(run && run.success<run.total));
    $('notice').textContent=state.busy?'Kaynaklar taranıyor. Tamamlandığında liste otomatik yenilenir.':!run?'İlk tarama hazırlanıyor.':run.success===0?'Haber akışlarına erişilemedi. Mevcut arşiv gösteriliyor; internet bağlantısını ve Kaynaklar bölümünü kontrol edin.':`${run.success}/${run.total} akış erişilebilir. ${run.new} yeni kayıt eklendi. Konu ve ilçe etiketleri başlıktan otomatik çıkarılır.`;
    if(!archive.last_success || Date.now()-Date.parse(archive.last_success)>36*3600000){$('notice').classList.add('error');$('notice').textContent='Haberler güncel olmayabilir. Son başarılı tarama: '+(archive.last_success?date(archive.last_success):'bilinmiyor')+'. Mevcut arşiv gösteriliyor.';}
    if(state.unknown_dates)$('notice').textContent+=` Tarihi okunamayan ${state.unknown_dates} kayıt dönem listelerine alınmadı.`;
    render();clearTimeout(polling);polling=setTimeout(load,state.busy?1800:30000);
  }catch(e){$('refresh').disabled=false;$('notice').classList.add('error');$('notice').textContent='Haber dosyası alınamadı. İnternet bağlantınızı kontrol edip Listeyi yenile düğmesini deneyin. Varsa önceki liste ekranda korunur.';clearTimeout(polling);polling=setTimeout(load,10000);}
}
function render(){
  if(!state)return;
  $('view-title').textContent=({all:'Haber akışı',watch:'Takip ettiklerim',saved:'Kaydedilenler',sources:'Kaynaklar ve durum'})[view];
  $('filters').hidden=view==='sources';
  if(view==='sources'){
    $('result-count').textContent='Google Haberler RSS';
    $('articles').innerHTML='<div class="card"><h3>Tarama kapsamı</h3><p>Altı arama akışı, Google Haberler üzerinden Erzurum ve 20 ilçesini tarar. Akışlar farklı bağımsız kaynaklar değildir; aynı haber farklı sorgularda görünebilir. Yerel basın ve resmî kurumlar için arama yapılması, bu sitelerdeki tüm içeriklerin tarandığı anlamına gelmez.</p><p>İnternet gereklidir. Haberler GitHub üzerinde her gün Türkiye saati 08.00 için zamanlanmış görevle toplanır; çalışma saati gecikebilir. Listeyi yenile son yayımlanan veriyi getirir, yeni tarama başlatmaz. Notlar, kaydedilenler ve takip kelimeleri sadece bu tarayıcıda saklanır; başka cihazlara aktarılmaz. Tarayıcı verilerini silmek bunları siler.</p>'+(state.last_run?state.last_run.sources.map(s=>`<div class="source-row"><strong>${esc(s.name)}</strong><p class="${s.ok?'ok':'bad'}">${s.ok?'✓ Erişildi · '+s.count+' kayıt':'Erişilemedi · '+esc(s.error)}</p></div>`).join(''):'<p>Henüz tarama yapılmadı.</p>')+'</div>';return;
  }
  const q=fold($('search').value), district=$('district').value, category=$('category').value;
  let rows=state.articles.filter(a=>(view!=='saved'||a.saved)&&(view!=='watch'||matches(a).length)&&(!$('hide-weather').checked||a.category!=='Hava durumu')&&(!district||a.districts.includes(district))&&(!category||a.category===category)&&(!q||fold(a.title+' '+a.source+' '+a.note).includes(q)));
  const groups=new Map(); for(const a of rows){const key=$('dedup').checked?fold(a.title):a.id;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(a);}
  $('result-count').textContent=groups.size+' başlık · '+rows.length+' kayıt';
  if(!rows.length){$('articles').innerHTML='<div class="empty"><span style="font-size:32px">◎</span><h3>'+ (state.busy?'Haberler toplanıyor…':'Bu görünümde haber yok')+'</h3><p>'+(view==='saved'?'Bir haberdeki yıldız düğmesine basarak çalışma listenize ekleyin.':view==='watch'?'Takip kelimelerinizi düzenleyin veya zaman aralığını genişletin.':'Zaman aralığını genişletin, filtreleri temizleyin veya haberleri yeniden tarayın.')+'</p><p>Boş sonuç, kentte haber olmadığı anlamına gelmez.</p></div>';return;}
  $('articles').innerHTML=[...groups.values()].map(group=>{
    const a=group[0], hit=matches(a);
    return `<article class="card"><div class="card-top"><span class="tag">${esc(a.category)}</span><span class="district">${esc(a.districts.join(' · '))}</span>${hit.length?'<span class="tag matched">◎ '+esc(hit.join(', '))+'</span>':''}</div><h3><a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${esc(a.title)}</a></h3><div class="meta"><strong>${esc(a.source)}</strong><span>·</span><time>${date(a.published)}</time></div>${group.length>1?'<div class="duplicates">Diğer yayınlar: '+group.slice(1).map(r=>`<a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.source)}</a>`).join('')+'</div>':''}${a.note?'<p class="user-note">'+esc(a.note)+'</p>':''}<div class="card-bottom"><a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">Kaynağında oku ↗</a><button data-note="${a.id}">✎ Not ekle</button><button data-save="${a.id}" aria-label="${a.saved?'Kaydı kaldır':'Haberi kaydet'}">${a.saved?'★ Kaydedildi':'☆ Kaydet'}</button></div></article>`;
  }).join('');
}
$('today').textContent=new Date().toLocaleDateString('tr-TR',{timeZone:'Europe/Istanbul',weekday:'long',day:'numeric',month:'long',year:'numeric'})+' · Yerel gündem takibi';
for(const id of ['search','district','category','dedup','hide-weather'])$(id).addEventListener(id==='search'?'input':'change',render);
$('period').addEventListener('change',load);
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{view=b.dataset.view;document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('active',x===b));render();}));
$('refresh').addEventListener('click',async()=>{try{$('refresh').disabled=true;await post('/api/refresh',{});await load();}catch(e){toast(e.message);$('refresh').disabled=false;}});
$('save-watch').addEventListener('click',async()=>{try{const words=[...new Set($('watch-input').value.split(',').map(w=>w.trim()).filter(Boolean))];if(words.length>30||words.some(w=>w.length>60))return toast('En fazla 30 kelime; her biri en fazla 60 karakter olmalı.');await post('/api/watch',{words});await load();toast('Takip listeniz kaydedildi.');}catch(e){toast(e.message);}});
$('export').addEventListener('click',()=>{if(state)exportCsv();});
$('brief-download').addEventListener('click',e=>{e.preventDefault();if(archive)exportBrief();});
$('articles').addEventListener('click',async e=>{const save=e.target.closest('[data-save]'),note=e.target.closest('[data-note]');try{if(save){const a=state.articles.find(a=>a.id===save.dataset.save);await post('/api/article',{id:a.id,saved:!a.saved});await load();}if(note){editing=state.articles.find(a=>a.id===note.dataset.note);$('note-title').textContent=editing.title;$('note-text').value=editing.note;$('note-dialog').showModal();}}catch(err){toast(err.message);}});
$('save-note').addEventListener('click',async()=>{try{await post('/api/article',{id:editing.id,note:$('note-text').value});$('note-dialog').close();await load();toast('Not kaydedildi.');}catch(e){toast(e.message);}});
load();
