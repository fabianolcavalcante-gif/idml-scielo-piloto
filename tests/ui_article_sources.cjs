const assert=require('node:assert/strict');
const vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const nodes=new Map();
function node(selector){if(!nodes.has(selector))nodes.set(selector,{value:'',textContent:'',innerHTML:'',disabled:false,hidden:false,handlers:{},children:[],addEventListener(event,fn){this.handlers[event]=fn},append(item){this.children.push(item)}});return nodes.get(selector)}
let requests=[];
const state={org:'org-a'};
const context=vm.createContext({state,$:node,document:{querySelector:node,createElement:()=>({})},Date,encodeURIComponent,crypto:{randomUUID:()=> 'fixed-request-id'},message:(n,text)=>n.textContent=text,api:(path,options)=>new Promise((resolve,reject)=>requests.push({path,options,resolve,reject}))});
vm.runInContext(input.js,context);
async function main(){
 const nav=node('[data-view="sources"]');
 let load=nav.handlers.click();requests.shift().resolve([{id:'article-a',title:'<img src=x onerror=bad>'}]);await load;
 assert.equal(node('#source-article').children[0].textContent,'<img src=x onerror=bad>');
 assert.ok(!node('#source-article').innerHTML.includes('<img'));
 node('#source-article').value='article-a';
 let first=node('#source-article').handlers.change();let old=requests.shift();
 node('#source-article').value='article-b';let latest=node('#source-article').handlers.change();
 requests.shift().resolve({status:'active',sequence:3,can_manage:false});await latest;
 old.resolve({status:'active',sequence:1,can_manage:true});await first;
 assert.equal(node('#source-grant').disabled,true);
 let refresh=node('#source-article').handlers.change();requests.shift().resolve({status:'active',sequence:3,can_manage:true});await refresh;
 node('#source-days').value='7';
 let grant=node('#source-grant').handlers.click();let post=requests.shift();
 assert.equal(post.path,'/v1/resources/article-b/public-sources');
 assert.deepEqual(JSON.parse(post.options.body),{request_id:'fixed-request-id',expected_sequence:3,action:'grant',days:7});
 state.org='org-b';node('#organization').handlers.change();
 post.resolve({status:'active'});await grant;
 assert.equal(node('#source-grant').disabled,true);
 assert.ok(!node('#source-message').textContent.includes('Consultas autorizadas'));
 // A slow read for another organization must not restore its controls.
 const pending=requests.shift();state.org='org-c';node('#organization').handlers.change();
 pending.resolve([]);await Promise.resolve();
 assert.equal(node('#source-grant').disabled,true);
 console.log('source UI: selection, safe text, authorization payload and tenant races passed');
}
main().catch(error=>{console.error(error);process.exitCode=1});
