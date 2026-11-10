(()=>{const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),money=n=>'Rs. '+Number(n).toFixed(2),fetchH={'X-Requested-With':'fetch'};
// scroll progress + back to top
const bar=$('#progress'),top=$('#toTop');
addEventListener('scroll',()=>{const h=document.documentElement,p=h.scrollTop/(h.scrollHeight-h.clientHeight||1);bar.style.width=p*100+'%';top.classList.toggle('show',h.scrollTop>500)},{passive:true});
top.onclick=()=>scrollTo({top:0,behavior:'smooth'});
// toast
function toast(m){const t=document.createElement('div');t.className='toast';t.textContent=m;$('#toasts').append(t);setTimeout(()=>t.remove(),3500)}
$$('.flash').forEach(f=>{toast(f.textContent);f.remove()});
// cursor glow
const cg=$('#cursorGlow');if(matchMedia('(pointer:fine)').matches)addEventListener('pointermove',e=>{cg.style.left=e.clientX+'px';cg.style.top=e.clientY+'px'});
// 3D scene: floating polyhedra + rings + depth dust; reacts to mouse, scroll and click
const cv=$('#stars'),cx=cv.getContext('2d'),root=document.documentElement;let W,H,R=1;const LOW=(navigator.hardwareConcurrency||8)<=4||(navigator.deviceMemory||8)<=4||innerWidth<700;
const G={cube:{v:[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],f:[[0,1,2,3],[4,5,6,7],[0,1,5,4],[2,3,7,6],[1,2,6,5],[0,3,7,4]]},
 oct:{v:[[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]],f:[[0,2,4],[2,1,4],[1,3,4],[3,0,4],[2,0,5],[1,2,5],[3,1,5],[0,3,5]]},
 tet:{v:[[1,1,1],[-1,-1,1],[-1,1,-1],[1,-1,-1]],f:[[0,1,2],[0,3,1],[0,2,3],[1,3,2]]},
 ring:{v:Array.from({length:28},(_,i)=>[Math.cos(i/28*6.2832),Math.sin(i/28*6.2832),0]),ring:1}};
const PAL={dark:[[192,132,252],[236,72,153],[129,140,248],[244,114,182]],light:[[124,58,237],[219,39,119],[59,130,246],[168,85,247]]};
let sh=[],dust=[],M={x:0,y:0,sx:0,sy:0,px:-999,py:-999},SC=0,pulse=0;
const rnd=(a,b)=>a+Math.random()*(b-a);
function build(){W=innerWidth;H=innerHeight;R=LOW?1:Math.min(devicePixelRatio||1,1.5);cv.width=W*R;cv.height=H*R;cv.style.width=W+'px';cv.style.height=H+'px';
 const n=LOW?6:16,kinds=['cube','oct','tet','cube','oct','ring'];
 sh=Array.from({length:n},(_,i)=>({g:G[kinds[i%kinds.length]],x:rnd(-.6,.6)*W,y:rnd(-.7,.7)*H,z:rnd(80,900),s:rnd(26,70)*(W<700?.55:1),rx:rnd(0,6),ry:rnd(0,6),vx:rnd(-.012,.012),vy:rnd(-.015,.015),c:i%4,ox:0,oy:0}));
 dust=Array.from({length:LOW?30:130},()=>({x:rnd(-.7,.7)*W,y:rnd(-.7,.7)*H,z:rnd(0,1100),c:Math.floor(rnd(0,4))}))}
build();addEventListener('resize',build);
addEventListener('pointermove',e=>{M.x=e.clientX/W-.5;M.y=e.clientY/H-.5;M.px=e.clientX;M.py=e.clientY},{passive:true});
addEventListener('pointerdown',e=>{pulse=1;M.px=e.clientX;M.py=e.clientY});
addEventListener('scroll',()=>SC=scrollY,{passive:true});
const F=700,Z0=500;
function proj(x,y,z,a,b,sy){y-=sy;const x1=x*Math.cos(a)+(z-Z0)*Math.sin(a),z1=-x*Math.sin(a)+(z-Z0)*Math.cos(a)+Z0,y1=y*Math.cos(b)-(z1-Z0)*Math.sin(b),z2=y*Math.sin(b)+(z1-Z0)*Math.cos(b)+Z0,k=F/(F+z2);return[W/2+x1*k,H/2+y1*k,k,z2]}
function rot(v,rx,ry){let[x,y,z]=v,c=Math.cos(rx),s=Math.sin(rx),y1=y*c-z*s,z1=y*s+z*c;c=Math.cos(ry);s=Math.sin(ry);return[x*c+z1*s,y1,-x*s+z1*c]}
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
let fN=0,fT=0,fSlow=0;
function frame(t){if(t){if(fT){fN++;if(t-fT>45)fSlow++;if(fN>=90){if(fSlow>30){cv.style.display='none';root.classList.add('lite');return}fN=fSlow=0}}fT=t}M.sx+=(M.x-M.sx)*.06;M.sy+=(M.y-M.sy)*.06;const light=root.dataset.theme==='light',P=PAL[light?'light':'dark'],a=M.sx*.55,b=-M.sy*.35;
 cx.setTransform(R,0,0,R,0,0);cx.clearRect(0,0,W,H);
 const span=H*1.5;
 for(const d of dust){d.z-=.6;if(d.z<0)d.z=1100;const sy=SC*(.05+(1-d.z/1100)*.25),yy=((d.y-sy+span/2)%span+span)%span-span/2+sy,p=proj(d.x,yy,d.z,a,b,sy),c=P[d.c];cx.fillStyle=`rgba(${c},${Math.min(1,.2+p[2]*.9)*(light?.75:.9)})`;cx.beginPath();cx.arc(p[0],p[1],Math.max(.5,p[2]*2.6),0,7);cx.fill()}
 const items=sh.map(o=>{o.rx+=o.vx;o.ry+=o.vy;const sy=SC*(.06+(1-o.z/900)*.22),yy=((o.y-sy+span/2)%span+span)%span-span/2+sy,p=proj(o.x,yy,o.z,a,b,sy);
  const dx=p[0]+o.ox-M.px,dy=p[1]+o.oy-M.py,d=Math.hypot(dx,dy)||1,rad=pulse?340:170;if(d<rad){const f=(1-d/rad)*(pulse?26:5);o.ox+=dx/d*f;o.oy+=dy/d*f;o.vy+=.0008*(dx>0?1:-1)}
  o.ox*=.93;o.oy*=.93;o.vy*=.995;return{o,p,sy,yy}}).sort((u,v)=>v.p[3]-u.p[3]);pulse=0;
 for(const{o,p,sy,yy}of items){const c=P[o.c],k=p[2],g=o.g,pts=g.v.map(v=>{const r=rot(v,o.rx,o.ry);return proj(o.x+r[0]*o.s,yy+r[1]*o.s,o.z+r[2]*o.s,a,b,sy)}).map(q=>[q[0]+o.ox,q[1]+o.oy,q[3]]);
  cx.lineJoin='round';cx.shadowColor=`rgba(${c},.8)`;cx.shadowBlur=LOW?0:light?6:14;cx.strokeStyle=`rgba(${c},${light?.85:.8})`;cx.lineWidth=Math.max(1,2.2*k);
  if(g.ring){cx.beginPath();pts.forEach((q,i)=>i?cx.lineTo(q[0],q[1]):cx.moveTo(q[0],q[1]));cx.closePath();cx.stroke();continue}
  [...g.f].sort((u,v)=>u.reduce((s,i)=>s+pts[i][2],0)/u.length<v.reduce((s,i)=>s+pts[i][2],0)/v.length?1:-1).forEach((f,i)=>{cx.beginPath();f.forEach((j,n)=>n?cx.lineTo(pts[j][0],pts[j][1]):cx.moveTo(pts[j][0],pts[j][1]));cx.closePath();cx.fillStyle=`rgba(${c},${(light?.22:.16)+(i%3)*.05})`;cx.fill();cx.stroke()})}
 cx.shadowBlur=0;if(!still)requestAnimationFrame(LOW?()=>requestAnimationFrame(frame):frame)}
frame();
// generic 3D tilt with glare
if(matchMedia('(pointer:fine)').matches&&!still)$$('.product-card,.detail-image,.auth-card,.promo,.cart-item,.stat-card,.trust div,.review,.empty-state,.success-page').forEach(el=>{el.classList.add('tilt');
 el.addEventListener('pointermove',e=>{const r=el.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;el.style.setProperty('--rx',(-y*12)+'deg');el.style.setProperty('--ry',(x*14)+'deg');el.style.setProperty('--mx',(x+.5)*100+'%');el.style.setProperty('--my',(y+.5)*100+'%')});
 el.addEventListener('pointerleave',()=>{el.style.setProperty('--rx','0deg');el.style.setProperty('--ry','0deg')})});
// typed words
const ty=$('#typed');if(ty){const w=ty.dataset.words.split('|');let i=0,c=w[0].length,del=true;(function t(){const cur=w[i];ty.textContent=cur.slice(0,c);if(del){c--;if(c<0){del=false;i=(i+1)%w.length;c=0}setTimeout(t,45)}else{c++;if(c>w[i].length){del=true;c=w[i].length;return setTimeout(t,1800)}setTimeout(t,85)}})();ty.textContent=w[0]}
// ripple on buttons
document.addEventListener('click',e=>{const b=e.target.closest('.btn');if(!b)return;const r=b.getBoundingClientRect(),d=Math.max(r.width,r.height),s=document.createElement('span');s.className='ripple';s.style.cssText=`width:${d}px;height:${d}px;left:${e.clientX-r.left-d/2}px;top:${e.clientY-r.top-d/2}px`;b.append(s);setTimeout(()=>s.remove(),600)});
// cart: drawer + ajax add
const cc=$('#cartCount');
function setCount(n){cc.textContent=n;cc.classList.remove('bump');void cc.offsetWidth;cc.classList.add('bump')}
async function loadDrawer(){const d=await (await fetch('/api/cart')).json();$('#drawerBody').innerHTML=d.items.length?d.items.map(i=>`<div class="d-item">${i.image?`<img src="${i.image}" alt="">`:'<div class="ph">S</div>'}<div><a href="${i.url}"><b></b></a><small>${i.variant?esc(i.variant)+' · ':''}${i.qty} × ${money(i.price)}</small></div><b>${money(i.line)}</b></div>`).join(''):'<p class="muted" style="text-align:center;padding:40px 0">Your bag is empty ✦</p>';
 $$('#drawerBody .d-item a b').forEach((el,k)=>el.textContent=d.items[k].name);$('#drawerTotal').textContent=money(d.total);setCount0(d.count)}
function setCount0(n){cc.textContent=n}
const openD=()=>{document.body.classList.add('drawer-open');loadDrawer()},closeD=()=>document.body.classList.remove('drawer-open');
$('#cartBtn').addEventListener('click',e=>{if(location.pathname==='/cart'||location.pathname==='/checkout')return;e.preventDefault();openD()});
$('#drawerClose').onclick=closeD;$('#drawerBg').onclick=closeD;addEventListener('keydown',e=>e.key==='Escape'&&closeD());
document.addEventListener('submit',async e=>{const f=e.target.closest('.ajax-add');if(!f)return;if(e.submitter&&e.submitter.name==='buy')return;e.preventDefault();const btn=f.querySelector('.add-btn,button.primary'),old=btn.textContent;
 try{const r=await fetch(f.action,{method:'POST',body:new FormData(f),headers:fetchH});const d=await r.json();if(!d.ok){toast('⚠ '+d.message);return}setCount(d.count);toast('✓ '+d.message);btn.classList.add('added');btn.textContent='Added ✓';setTimeout(()=>{btn.classList.remove('added');btn.textContent=old},1500)}catch(_){f.submit()}});
// steppers (+ auto-update on cart page)
document.addEventListener('click',e=>{const b=e.target.closest('.stepper button');if(!b)return;const i=$('input',b.parentElement),min=+i.min||0,max=+i.max||99;i.value=Math.max(min,Math.min(max,(+i.value||0)+ +b.dataset.step));const cf=$('#cartForm');if(cf){clearTimeout(cf._t);cf._t=setTimeout(()=>cf.submit(),700)}});
// shop: instant search + sort
const grid=$('#grid'),q=$('#shopFilters input[name=q]'),sortSel=$('#sortSel');
if(grid){const cards=$$('.product-card',grid);const apply=()=>{const t=(q.value||'').toLowerCase();cards.forEach(c=>c.style.display=c.dataset.name.includes(t)?'':'none');
 if(sortSel.value){[...cards].sort((a,b)=>sortSel.value==='lo'?a.dataset.price-b.dataset.price:b.dataset.price-a.dataset.price).forEach(c=>grid.append(c))}};
 q.addEventListener('input',apply);sortSel.addEventListener('change',apply);$('#shopFilters select[name=category]').addEventListener('change',e=>e.target.form.submit())}
// product: image zoom + star picker
$$('.zoom').forEach(z=>z.addEventListener('pointermove',e=>{const r=z.getBoundingClientRect();z.style.setProperty('--zx',(e.clientX-r.left)/r.width*100+'%');z.style.setProperty('--zy',(e.clientY-r.top)/r.height*100+'%')}));
const sp=$('#starPick');if(sp){const sel=$('#ratingSel'),paint=v=>$$('i',sp).forEach(s=>s.classList.toggle('on',+s.dataset.v<=v));paint(5);sp.addEventListener('click',e=>{const s=e.target.closest('i');if(s){sel.value=s.dataset.v;paint(+s.dataset.v)}});sp.addEventListener('pointerover',e=>{const s=e.target.closest('i');if(s)paint(+s.dataset.v)});sp.addEventListener('pointerleave',()=>paint(+sel.value))}
// checkout: copy payment details
$('#copyPay')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(window._payText||'');toast('Payment details copied ✓')}catch(_){toast('Copy failed — select the text manually')}});
// admin stat count-up
$$('.stat-card b').forEach(b=>{const m=b.textContent.match(/\d[\d,]*\.?\d*/);if(!m)return;const end=parseFloat(m[0].replace(/,/g,'')),dec=m[0].includes('.')?2:0,pre=b.textContent.slice(0,m.index);let n=0;const st=performance.now();(function f(t){n=Math.min(1,(t-st)/900);b.textContent=pre+(end*n).toFixed(dec);n<1&&requestAnimationFrame(f)})(st)});

// admin: live discount preview
$$('[data-preview]').forEach(box=>{const f=box.closest('form'),o=f.elements.price,s=f.elements.sale_price,up=()=>{const a=+o.value,b=s.value===''?a:+s.value;box.classList.remove('bad');if(!a){box.textContent='Enter the original price to see the preview.';return}if(b>a){box.classList.add('bad');box.textContent='⚠ Sale price must be lower than the original price.';return}const d=(1-b/a)*100;box.innerHTML=d>0?`Customers will see: <del>Rs. ${a.toFixed(2)}</del> <b>Rs. ${b.toFixed(2)}</b> <em class="off">${Math.round(d)}% OFF</em>`:`Customers will see: <b>Rs. ${a.toFixed(2)}</b> (no discount)`};o.addEventListener('input',up);s.addEventListener('input',up);up()});
})();
// product gallery (images + videos) and admin media picker
(()=>{const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const g=$('#gallery');if(g){const stage=$('#stage'),th=$$('.thumb',g),cnt=$('#gCount');let i=0;
 function show(n){if(!th.length)return;i=(n+th.length)%th.length;const t=th[i];stage.innerHTML='';
  if(t.dataset.kind==='video'){const v=document.createElement('video');v.src=t.dataset.src;v.controls=true;v.playsInline=true;v.preload='metadata';if(t.dataset.poster)v.poster=t.dataset.poster;stage.append(v);stage.classList.add('is-video')}
  else{const im=document.createElement('img');im.src=t.dataset.src;im.alt='';stage.append(im);stage.classList.remove('is-video')}
  th.forEach((x,k)=>x.classList.toggle('on',k===i));t.scrollIntoView({block:'nearest',inline:'center',behavior:'smooth'});if(cnt)cnt.textContent=(i+1)+' / '+th.length}
 th.forEach((t,k)=>t.onclick=()=>show(k));$('.g-nav.prev',g)?.addEventListener('click',()=>show(i-1));$('.g-nav.next',g)?.addEventListener('click',()=>show(i+1));
 addEventListener('keydown',e=>{if(/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))return;if(e.key==='ArrowLeft')show(i-1);if(e.key==='ArrowRight')show(i+1)});
 let sx=null;stage.addEventListener('touchstart',e=>sx=e.touches[0].clientX,{passive:true});stage.addEventListener('touchend',e=>{if(sx===null)return;const d=e.changedTouches[0].clientX-sx;if(Math.abs(d)>50)show(i+(d<0?1:-1));sx=null})}
const inp=$('[data-media-input]'),prev=$('[data-media-preview]');
if(inp&&prev){const cloud=inp.dataset.cloudName?{n:inp.dataset.cloudName,p:inp.dataset.cloudPreset}:null,hid=$('#mediaUrls');let items=[];
 const isVid=f=>f.type.startsWith('video'),ok=f=>(f.type.startsWith('image/')&&f.size<=8*1048576)||(isVid(f)&&f.size<=100*1048576);
 const out=()=>{if(hid)hid.value=JSON.stringify(items.filter(i=>i.url).map(i=>({url:i.url,kind:i.kind})))};
 function syncLocal(){if(cloud)return;const dt=new DataTransfer();items.forEach(i=>dt.items.add(i.file));inp.files=dt.files}
 function render(){prev.innerHTML='';items.forEach((it,k)=>{const d=document.createElement('div');d.className='mp-item';const m=isVid(it.file)?document.createElement('video'):document.createElement('img');m.src=it.src;if(m.tagName==='VIDEO'){m.muted=true;m.preload='metadata'}
  const x=document.createElement('button');x.type='button';x.className='x';x.textContent='×';x.onclick=()=>{if(it.xhr)it.xhr.abort();items.splice(k,1);out();syncLocal();render()};
  const n=document.createElement('span');n.className='name';n.textContent=(isVid(it.file)?'🎬 ':'🖼 ')+it.file.name+(it.err?' — '+it.err:it.url?' ✓':cloud?' — '+it.pct+'%':'');d.append(m,x,n);
  if(cloud&&!it.url&&!it.err){const b=document.createElement('i');b.className='bar';b.style.width=it.pct+'%';d.append(b)}prev.append(d)})}
 function upload(it){const fd=new FormData();fd.append('file',it.file);fd.append('upload_preset',cloud.p);const x=new XMLHttpRequest();it.xhr=x;x.open('POST','https://api.cloudinary.com/v1_1/'+cloud.n+'/auto/upload');
  x.upload.onprogress=e=>{if(e.lengthComputable){it.pct=Math.round(e.loaded/e.total*100);render()}};
  x.onload=()=>{try{const r=JSON.parse(x.responseText);if(x.status<300&&r.secure_url){it.url=r.secure_url;it.kind=r.resource_type==='video'?'video':'image'}else it.err=(r.error&&r.error.message)||'Upload failed'}catch(e){it.err='Upload failed'}it.xhr=null;out();render()};
  x.onerror=()=>{it.err='Network error';it.xhr=null;render()};x.send(fd)}
 inp.addEventListener('change',()=>{const all=[...inp.files],fresh=all.filter(ok);if(fresh.length<all.length)alert('Some files were skipped (images up to 8 MB, videos up to 100 MB).');
  fresh.forEach(f=>{if(items.length<12){const it={file:f,src:URL.createObjectURL(f),pct:0,kind:isVid(f)?'video':'image'};items.push(it);if(cloud)upload(it)}});
  if(cloud)inp.value='';else syncLocal();render()});
 const form=inp.closest('form');if(form)form.addEventListener('submit',e=>{if(!cloud)return;if(items.some(i=>!i.url&&!i.err)){e.preventDefault();alert('Please wait until the uploads finish.')}else if(items.some(i=>i.err)){e.preventDefault();alert('Remove the files that failed to upload, then try again.')}})}

// product options: chosen text + friendly "please select" message; admin colour/size editor
$$('.opt-group').forEach(g=>g.addEventListener('change',e=>{if(e.target.type!=='radio')return;const c=$('.opt-chosen',g);if(c)c.textContent=e.target.value;g.classList.remove('missing');const m=$('.opt-msg',g);if(m)m.hidden=true}));
document.addEventListener('invalid',e=>{const r=e.target,g=r.type==='radio'&&r.closest('.opt-group');if(!g)return;e.preventDefault();g.classList.remove('shake');void g.offsetWidth;g.classList.add('missing','shake');const m=$('.opt-msg',g);if(m)m.hidden=false;g.scrollIntoView({block:'center',behavior:'smooth'})},true);
$$('.opt-editor').forEach(ed=>{const inp=$('[data-opt-input]',ed),pv=$('[data-opt-preview]',ed),list=()=>inp.value.split(/[,\n]+/).map(s=>s.trim()).filter(Boolean);
 const draw=()=>{pv.innerHTML='';const l=list();l.forEach(v=>{const c=document.createElement('span');c.className='chip-pill';c.textContent=v;pv.append(c)});$$('[data-preset]',ed).forEach(b=>b.classList.toggle('on',l.some(x=>x.toLowerCase()===b.dataset.preset.toLowerCase())))};
 $$('[data-preset]',ed).forEach(b=>b.addEventListener('click',()=>{const v=b.dataset.preset,l=list(),k=l.findIndex(x=>x.toLowerCase()===v.toLowerCase());if(k>=0)l.splice(k,1);else l.push(v);inp.value=l.join(', ');draw()}));
 inp.addEventListener('input',draw);draw()});
})();
