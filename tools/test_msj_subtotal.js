// Simulate the actual MSJ customer-order subtotal JavaScript without a browser or payments.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('msj_store.py','utf8');
const marker='/* V143_SUBTOTAL_READY';
const pos=src.indexOf(marker);
assert.ok(pos>=0,'V143 order total script missing');
let js=src.substring(pos,src.indexOf('</script>',pos));
assert.ok(js.includes('{{ garment_prices|tojson }}'));
js=js.replace('{{ garment_prices|tojson }}',JSON.stringify({'T-shirt':25000,'Hoodie':50000,'Cap':20000}));
function element(value){
  return {value,listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}}
}
const garment=element('T-shirt');
const quantity=element('1');
const subtotal={textContent:''};
const document={getElementById(id){return {garment,quantity,'order-subtotal':subtotal}[id]||null;}};
vm.runInNewContext(js,{document,Number,console});
assert.equal(subtotal.textContent,'MK 25,000');
quantity.value='2';quantity.listeners.input();
assert.equal(subtotal.textContent,'MK 50,000');
garment.value='Hoodie';garment.listeners.change();
assert.equal(subtotal.textContent,'MK 100,000');
quantity.value='3';quantity.listeners.input();
assert.equal(subtotal.textContent,'MK 150,000');
garment.value='Cap';garment.listeners.change();
assert.equal(subtotal.textContent,'MK 60,000');
quantity.value='0';quantity.listeners.input();
assert.equal(subtotal.textContent,'Check selection');
quantity.value='31';quantity.listeners.input();
assert.equal(subtotal.textContent,'Check selection');
quantity.value='1.5';quantity.listeners.input();
assert.equal(subtotal.textContent,'Check selection');
quantity.value='1';quantity.listeners.input();
assert.equal(subtotal.textContent,'MK 20,000');
console.log('PASS MSJ mobile subtotal JS: T-shirts, hoodies, caps, quantity changes and invalid quantities');
