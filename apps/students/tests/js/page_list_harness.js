// student-browser.js 의 pageList(page, pages)를 Node 에서 실행합니다. 사용: node page_list_harness.js <script> <json [[page,pages],...]>
const fs = require('fs');
const vm = require('vm');
const [script, payload] = process.argv.slice(2);
const sandbox = { window: {}, document: { readyState: 'complete', addEventListener() {}, querySelectorAll: () => [], querySelector: () => null }, location: { href: 'http://x/', origin: 'http://x' } };
sandbox.window.document = sandbox.document;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(script, 'utf8'), sandbox);
process.stdout.write(JSON.stringify(JSON.parse(payload).map(([p, n]) => sandbox.window.EduStudentBrowser.pageList(p, n))));
