// Starts the DIGITAL TWIN: a full private replica of the live game.
//   node scripts/run_twin.js        then open http://localhost:8080
// - the live game bundle, rebuilt from source/, pointed at a SANDBOX relay (ws://localhost:8787)
// - the real relay-server code, running locally
// Nothing here can touch real players. Open it in several tabs/browsers to play a full multiplayer game.
const http = require('http'), fs = require('fs'), path = require('path'), { spawn, execSync, execFileSync } = require('child_process');
const root = path.join(__dirname, '..');
const WEB = +process.env.TWIN_WEB_PORT || 8080, RELAY = +process.env.TWIN_RELAY_PORT || 8787;

function start(web, relay, quiet) {
  process.env.TWIN_RELAY_URL = 'ws://localhost:' + relay;
  execFileSync(process.execPath, ['scripts/make_twin.js'], { cwd: root, stdio: quiet ? 'pipe' : 'inherit', env: process.env });
  const page = fs.readFileSync(path.join(root, 'twin', 'site', 'index.html'));
  const web_srv = http.createServer((q, r) => { r.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); r.end(page); }).listen(web);
  const rdir = path.join(root, 'relay-server');
  let relayProc = null, relayNote = 'relay: running';
  if (!fs.existsSync(path.join(rdir, 'node_modules', 'ws'))) {
    try { execSync('npm install --omit=dev --no-audit --no-fund --no-package-lock', { cwd: rdir, stdio: 'pipe' }); }
    catch (e) { relayNote = 'relay: NOT started (could not install the "ws" package; run npm install in relay-server/)'; }
  }
  if (fs.existsSync(path.join(rdir, 'node_modules', 'ws'))) {
    relayProc = spawn(process.execPath, ['server.js'], { cwd: rdir, env: Object.assign({}, process.env, { PORT: String(relay) }), stdio: 'ignore' });
  }
  return { stop() { web_srv.close(); if (relayProc) relayProc.kill(); }, relayOk: !!relayProc, relayNote };
}
module.exports = { start };

if (require.main === module) {
  const t = start(WEB, RELAY, false);
  console.log('\nDIGITAL TWIN is up.  Open http://localhost:' + WEB + '   (' + t.relayNote + ' on ws://localhost:' + RELAY + ')');
  console.log('Press Ctrl+C to stop.');
  process.on('SIGINT', () => { t.stop(); process.exit(0); });
}
