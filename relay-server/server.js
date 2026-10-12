const { WebSocketServer } = require('ws');
const http = require('http');
const rooms = new Map();
const server = http.createServer((req, res) => { res.writeHead(200); res.end('relay ok\n'); });
const wss = new WebSocketServer({ server });
wss.on('connection', (ws, req) => {
  const url = new URL(req.url, 'http://localhost');
  const room = url.searchParams.get('room');
  if (!room) { ws.close(); return; }
  if (!rooms.has(room)) rooms.set(room, new Set());
  rooms.get(room).add(ws);
  ws.on('message', (data) => {
    for (const client of rooms.get(room)) {
      if (client.readyState === 1) client.send(data.toString('utf8'));
    }
  });
  ws.on('close', () => {
    rooms.get(room).delete(ws);
    if (rooms.get(room).size === 0) rooms.delete(room);
  });
});
const PORT = process.env.PORT || 8787;
server.listen(PORT, () => console.log('relay listening on', PORT));
