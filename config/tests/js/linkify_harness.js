// linkify.js 의 split()을 Node 에서 실행합니다. 사용: node linkify_harness.js <script> <json 문자열 배열>
const fs = require('fs');
const vm = require('vm');
const [script, payload] = process.argv.slice(2);
const listeners = {};
const sandbox = {
  window: {},
  document: { readyState: 'loading', addEventListener: (type, fn) => { listeners[type] = fn; } },
  MutationObserver: function () { this.observe = () => {}; },
};
sandbox.window.document = sandbox.document;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(script, 'utf8'), sandbox);
const out = JSON.parse(payload).map(text => sandbox.window.EduLinkify.split(text));
process.stdout.write(JSON.stringify(out));
