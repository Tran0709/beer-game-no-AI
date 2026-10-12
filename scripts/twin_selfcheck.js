// Proves the twin really works: page is served, and (if the relay's "ws" package is installed) a WebSocket connects.
const http = require('http'), path = require('path');
const { start } = require('./run_twin.js');
const WEB = 18080 + Math.floor(Math.random() * 500), RELAY = WEB + 1000;
const t = start(WEB, RELAY, true);
const done = (code, msg) => { console.log(msg); t.stop(); setTimeout(() => process.exit(code), 100); };
setTimeout(() => {
  http.get('http://localhost:' + WEB, res => {
    let b = ''; res.on('data', d => b += d); res.on('end', () => {
      if (res.statusCode !== 200 || !b.includes('The Beer Game')) return done(1, 'TWIN FAIL: page not served correctly');
      if (!b.includes("DEFAULT_SERVER_URL = 'ws://localhost:" + RELAY + "'")) return done(1, 'TWIN FAIL: not wired to the sandbox relay');
      if (!t.relayOk) return done(0, 'Twin page OK (relay check skipped: "ws" not installed)');
      let WS; try { WS = require(path.join(__dirname, '..', 'relay-server', 'node_modules', 'ws')); } catch (e) { return done(0, 'Twin page OK (relay check skipped)'); }
      const ws = new WS('ws://localhost:' + RELAY); const to = setTimeout(() => done(1, 'TWIN FAIL: relay did not accept a connection'), 4000);
      ws.on('open', () => { clearTimeout(to); ws.close(); done(0, 'Twin OK: page served, wired to sandbox relay, relay accepts connections'); });
      ws.on('error', e => { clearTimeout(to); done(1, 'TWIN FAIL: relay error ' + e.message); });
    });
  }).on('error', e => done(1, 'TWIN FAIL: ' + e.message));
}, 1500);
