(()=>{const box=document.getElementById('chat');if(!box)return;
const q=s=>box.querySelector(s),list=q('#msgs'),quick=q('#quick'),form=q('#chatForm'),txt=q('#chatText'),file=q('#chatFile'),note=q('#chatNote');
const role=box.dataset.role,api=box.dataset.api,post=box.dataset.post,H={'X-Requested-With':'fetch'};
let idle=0,last=0,queue=[],running=false,quickData=[],seen=new Set(),firstLoad=true,support='Support';
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
const WHO={bot:'🤖 Stark Assistant',customer:role==='agent'?'👤 Customer':'You'};
function bubble(m){
 if(m.sender==='system')return el('div','msg system',m.body);
 const mine=(role==='customer'&&m.sender==='customer')||(role==='agent'&&m.sender==='agent');
 const d=el('div','msg '+m.sender+(mine?' mine':''));d.append(el('small','who',m.sender==='agent'?'🧑‍💼 '+support:WHO[m.sender]));
 if(m.body)d.append(el('div','body',m.body));
 if(m.image){const a=el('a','shot');a.href=m.image;a.target='_blank';const i=document.createElement('img');i.src=m.image;i.alt='Screenshot';a.append(i);d.append(a)}
 if(m.extra){const b=el('button','copy','📋 Copy number');b.type='button';b.onclick=async()=>{try{await navigator.clipboard.writeText(m.extra);b.textContent='✓ Copied'}catch(e){b.textContent=m.extra}};d.append(b)}
 d.append(el('small','time',m.time));return d}
const bottom=()=>{list.scrollTop=list.scrollHeight};
function typing(){const t=el('div','msg bot typing');t.innerHTML='<i></i><i></i><i></i>';list.append(t);bottom();return t}
async function run(){if(running)return;running=true;quick.hidden=true;
 while(queue.length){const m=queue.shift();
  if(m._t){const t=typing();await new Promise(r=>setTimeout(r,650+Math.min(900,(m.body||'').length*7)));t.remove()}
  list.append(bubble(m));bottom()}
 running=false;renderQuick()}
function renderQuick(){quick.innerHTML='';if(role!=='customer'||running||queue.length||!quickData.length){quick.hidden=true;return}
 quickData.forEach(a=>{const b=el('button','qbtn',a.label);b.type='button';b.onclick=()=>{b.disabled=true;const fd=new FormData();fd.append('action',a.action);send(fd)};quick.append(b)});quick.hidden=false;bottom()}
function status(d){
 const sp=document.getElementById('statusPill');if(sp){sp.textContent=d.status_label;sp.className='pill st-'+d.status}
 const pp=document.getElementById('payPill');if(pp)pp.textContent=d.payment_status;
 const steps=['Pending','Confirmed','Shipped','Delivered'],i=steps.indexOf(d.status);
 document.querySelectorAll('#timeline li').forEach(li=>li.classList.toggle('done',steps.indexOf(li.dataset.step)<=i&&i>=0));
 const ab=document.getElementById('attachBtn');if(ab)ab.classList.toggle('pulse',d.state==='await_payment');
 if(role==='customer')txt.placeholder=d.state==='await_new_address'?'Type your full address…':d.state==='await_payment'?'Attach your payment screenshot with 📎':'Type a message…'}
async function poll(){try{const r=await fetch(api+'?after='+last,{headers:H});if(!r.ok)return 0;const d=await r.json();support=d.support;
 const fresh=d.messages.filter(m=>!seen.has(m.id));fresh.forEach(m=>{seen.add(m.id);last=Math.max(last,m.id);m._t=role==='customer'&&m.sender==='bot'&&(!firstLoad||box.dataset.animate==='1');queue.push(m)});
 firstLoad=false;quickData=d.quick||[];status(d);queue.length?run():(running||renderQuick());return fresh.length}catch(e){return 0}}
async function send(fd){idle=0;note.textContent='';try{const r=await fetch(post,{method:'POST',body:fd,headers:H});if(r.status===413){note.textContent='That file is too large. Please send a smaller screenshot.';return}const d=await r.json();if(!d.ok)note.textContent=d.error||'Could not send.'}catch(e){note.textContent='Network error. Please try again.'}poll()}
async function shrink(f){if(!f||!f.type.startsWith('image/')||f.type==='image/gif'||f.size<1200000)return f;try{const bmp=await createImageBitmap(f),s=Math.min(1,1600/Math.max(bmp.width,bmp.height)),cv=document.createElement('canvas');cv.width=Math.round(bmp.width*s);cv.height=Math.round(bmp.height*s);cv.getContext('2d').drawImage(bmp,0,0,cv.width,cv.height);const b=await new Promise(r=>cv.toBlob(r,'image/jpeg',.82));return b&&b.size<f.size?new File([b],f.name.replace(/\.\w+$/,'')+'.jpg',{type:'image/jpeg'}):f}catch(e){return f}}
form.addEventListener('submit',async e=>{e.preventDefault();if(!txt.value.trim()&&!file.files.length)return;const fd=new FormData(form),f=file.files[0];if(f)fd.set('image',await shrink(f));txt.value='';file.value='';send(fd)});
file.addEventListener('change',()=>{if(file.files.length){note.textContent='Uploading…';form.requestSubmit()}});
async function tick(){if(!document.hidden){const n=await poll();idle=n?0:idle+1}setTimeout(tick,idle>8?12000:idle>3?7000:3500)}
document.addEventListener('visibilitychange',()=>{if(!document.hidden){idle=0;poll()}});
poll();setTimeout(tick,3500);
})();
