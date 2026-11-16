// Run against the shipped app.js, with a minimal DOM and controlled network responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodes = new Map();
function node(selector) {
  if (!nodes.has(selector)) nodes.set(selector, {
    innerHTML: '', textContent: '', hidden: false,
    addEventListener() {}, replaceChildren() { this.innerHTML = ''; this.textContent = ''; },
  });
  return nodes.get(selector);
}
const context = vm.createContext({
  document: {querySelector: node, querySelectorAll: () => []},
  sessionStorage: {getItem: () => null}, Headers, encodeURIComponent,
});
vm.runInContext(input.js, context);
context.sample = input.diagnosis;
const run = code => vm.runInContext(code, context);
async function main() {
  const rendered = run('renderDiagnosis(sample, "job-1")');
  for (const label of ['XML e pacote', 'Validadores e consultas', 'Homologação e entrega',
    'Bloqueantes', 'Fatais', 'Avisos', 'Limitação conhecida', 'não concede aprovação', 'Próxima ação:']) {
    assert.ok(rendered.includes(label), label);
  }
  context.malicious = {notice: '<script>notice</script>', items: [{
    category: 'xml', title: '<img src=x onerror=alert(1)>', status: 'observed',
    detail: '<script>detail</script>', report_sha256: '<script>hash</script>',
    next_action: '<script>action</script>', identifier_sha256: '<svg onload=alert(1)>',
    counts: {'<img>': '<svg onload=alert(1)>'},
  }]};
  const safe = run('renderDiagnosis(malicious, "<script>id</script>")');
  assert.ok(!safe.includes('<script>') && !safe.includes('<img') && !safe.includes('<svg'));
  assert.ok(safe.includes('&lt;script&gt;') && safe.includes('&lt;img'));

  run('state.org="org-a"; state.token="token-a"; var pending=[]; api=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));');
  const oldJob = run('loadDiagnosis("old")');
  const newJob = run('loadDiagnosis("new")');
  run('pending[1].resolve(sample)'); await newJob;
  run('pending[0].resolve(sample)'); await oldJob;
  assert.ok(node('#validation-diagnosis').innerHTML.includes('<code>new</code>'));

  const otherOrg = run('loadDiagnosis("org-a-job")');
  run('state.org="org-b"');
  const refreshing = run('loadJobs()');
  run('pending[2].resolve(sample)'); await otherOrg;
  assert.equal(node('#validation-diagnosis').innerHTML, '');
  run('pending[3].resolve([])'); await refreshing;

  const logout = run('loadDiagnosis("expired-session")');
  run('state.token=null; pending[4].resolve(sample)'); await logout;
  assert.equal(node('#validation-diagnosis').innerHTML, '');

  run('state.token="new-session"');
  const error = run('loadDiagnosis("bad")');
  run('pending[5].reject(new Error("<script>network</script>"))'); await error;
  assert.equal(node('#validation-diagnosis').textContent, '<script>network</script>');
  assert.equal(node('#validation-diagnosis').innerHTML, '');
  console.log(JSON.stringify({checks: 6, passed: true, real_browser: false}));
}
main().catch(error => { console.error(error); process.exitCode=1; });
