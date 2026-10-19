// Reproduces the intervention comparison in the README using the real game engine.
// Run from the package folder:  node analysis/intervention-scenario.js
const E = require('../source/engine.js');
const CHAIN = E.CHAIN, WEEKS = 16, DEMAND = 8;
function run(label, { retailerScript, iv, from = 7 }) {
  const ra = { facilitator: { id: 'H', name: 'F', isBot: false }, retailer: { id: 'R', name: 'R', isBot: !retailerScript }, wholesaler: { id: 'B', name: 'W', isBot: true }, distributor: { id: 'B', name: 'D', isBot: true }, manufacturer: { id: 'B', name: 'M', isBot: true } };
  const e = new E.BeerGameEngine({ roleAssignments: ra, totalWeeks: WEEKS });
  for (let w = 1; w <= WEEKS; w++) {
    if (iv && w === from) e.setInterventions(typeof iv === 'function' ? iv(e) : iv);
    const map = { facilitator: DEMAND };
    if (retailerScript) map.retailer = retailerScript(w, e.roles.retailer);
    e.processWeek(map);
  }
  const orders = r => e.roles[r].history.map(h => h.orderPlaced);
  const cost = r => e.roles[r].totalCost;
  const peak = r => Math.max(...orders(r).slice(2));
  const backlogEnd = CHAIN.reduce((s, r) => s + e.roles[r].backlog, 0);
  const chain = CHAIN.reduce((s, r) => s + cost(r), 0);
  return { label, chain, retailer: cost('retailer'), upstream: cost('wholesaler') + cost('distributor') + cost('manufacturer'), peakR: peak('retailer'), peakW: peak('wholesaler'), peakD: peak('distributor'), peakM: peak('manufacturer'), backlogEnd, base: e.baseline.total };
}
// a Retailer that understocks for four weeks, then panics: orders far more than it needs to clear the backlog
const spiral = (w, r) => (w <= 2 ? 4 : w <= 6 ? 2 : (r.backlog > 0 ? Math.min(80, 2 * r.backlog + 8) : DEMAND));
const rows = [
  run('0  healthy chain (all AI, steady demand 8)', { retailerScript: null }),
  run('1  PROBLEM: understocks, then panic-orders', { retailerScript: spiral }),
  run('2  + information sharing: whole chain', { retailerScript: spiral, iv: { infoScope: 'chain' } }),
  run('3  + information sharing: Wholesaler only', { retailerScript: spiral, iv: { infoScope: 'wholesaler' } }),
  run('4  + order ceiling 12 for 4 weeks', { retailerScript: spiral, iv: { caps: { retailer: { max: 12, untilWeek: 10 } } } }),
  run('5  + order ceiling 16 for 3 weeks', { retailerScript: spiral, iv: { caps: { retailer: { max: 16, untilWeek: 9 } } } }),
  run('6  + market shift: Retailer backlog $0.50', { retailerScript: spiral, iv: { costs: { retailer: { stockout: 0.5 } } } }),
  run('7  + ceiling 12 (4 wk) AND sharing (chain)', { retailerScript: spiral, iv: { infoScope: 'chain', caps: { retailer: { max: 12, untilWeek: 10 } } } }),
];
const pad = (s, n) => String(s).padEnd(n);
console.log(pad('scenario', 46) + pad('chain $', 9) + pad('retail $', 10) + pad('upstream $', 12) + pad('peak orders R/W/D/M', 22) + 'backlog left');
for (const r of rows) console.log(pad(r.label, 46) + pad(r.chain, 9) + pad(r.retailer, 10) + pad(r.upstream, 12) + pad(`${r.peakR}/${r.peakW}/${r.peakD}/${r.peakM}`, 22) + r.backlogEnd);
console.log('\n(16-week game, customers order 8 a week from week 3, interventions switched on at week 7)');
