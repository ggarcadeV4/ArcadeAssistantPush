const fs = require('fs');
const assert = require('assert');

function fileHas(any, haystack) {
  return any.some(tok => haystack.includes(tok));
}

describe('Gateway config routes safety', () => {
  it('routes/config.js contains no fs write APIs', () => {
    const text = fs.readFileSync('gateway/routes/config.js','utf-8');
    const banned = ['fs.writeFile', 'fs.appendFile', 'fs.rename', 'fs.rm', 'fs.rmdir', 'fs.mkdir', 'fs.copyFile', 'fs.createWriteStream', 'safeWrite('];
    assert.strictEqual(fileHas(banned, text), false, 'No fs write calls allowed in gateway config routes');
  });

  it('localProxy.js forwards x-device-id and x-panel headers', () => {
    const text = fs.readFileSync('gateway/routes/localProxy.js','utf-8');
    assert.ok(text.includes("'x-device-id': req.headers['x-device-id']"), 'Must forward x-device-id header');
    assert.ok(text.includes("'x-panel': req.headers['x-panel']"), 'Must forward x-panel header');
    assert.ok(text.includes("'x-corr-id': req.headers['x-corr-id']"), 'Must forward x-corr-id header');
  });
});
