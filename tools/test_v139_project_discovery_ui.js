// Test existing production script in an isolated DOM emulator, no browser/network.
const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
const source=fs.readFileSync('/tmp/ibrows_v139_discovery_ui.js','utf8');

function radio(value){
 return {value,checked:false,dataset:{},listeners:{},
   addEventListener(event,handler){(this.listeners[event]??=[]).push(handler)},
   fire(event){for(const fn of this.listeners[event]||[])fn.call(this)}};
}
const yes=radio('YES'),no=radio('NO');
const feature={type:'checkbox',checked:true};
const notes={value:'Test AI boundaries'};
const details={
 hidden:false,style:{display:''},
 querySelectorAll(q){
   if(q==='input[type="checkbox"]')return [feature];
   if(q==='textarea')return [notes];
   return [];
 }
};
const elements={'ai-details':details};
const document={
 readyState:'complete',
 querySelectorAll(q){
   if(q==='input[name="ai_interest"]')return [yes,no];
   return [];
 },
 querySelector(q){
   if(q==='input[name="ai_interest"]:checked')return yes.checked?yes:no.checked?no:null;
   return null;
 },
 getElementById(id){return elements[id]||null},
 addEventListener(){},
};
const window={
 setTimeout(fn){fn()},
 addEventListener(){},
};
no.checked=true;
vm.runInNewContext(source,{document,window,console,setTimeout:fn=>fn()},{timeout:1200});
assert(details.hidden===true && details.style.display==='none');
assert(feature.checked===false && notes.value==='');
no.checked=false;yes.checked=true;
yes.fire('change');
assert(details.hidden===false && details.style.display==='');
feature.checked=true;notes.value='New preferences';
yes.checked=false;no.checked=true;
no.fire('change');
assert(details.hidden && !feature.checked && notes.value==='');
no.checked=false;yes.checked=true;
yes.fire('change');
assert(!details.hidden && details.style.display==='');
assert(yes.dataset.ibrowsBound==='1' && no.dataset.ibrowsBound==='1');
console.log('PASS: Actual production Project Discovery JS switches NO→YES→NO→YES immediately, clears disabled AI fields, shows the form without page reload.');
