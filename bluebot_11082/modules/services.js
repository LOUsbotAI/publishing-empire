/* Reference native module. Copy this shape for every new screen.
   Rules: no fetch/XMLHttpRequest/WebSocket, no POST, no innerHTML with data, no 11884.
   Read data only with api.get(url); hand text to Louie with api.ask(text). */
(function () {
  'use strict';
  LoustaHub.register({
    id: 'services',
    title: 'Services',
    render(el, api) {
      const head = api.el('h1', '', 'Services');
      const sub = api.el('p', 'sub', 'Live status of every BlueBot service. Refreshes every 15 seconds.');
      const list = api.el('div', 'stack');
      el.append(head, sub, list);

      function draw() {
        const svcs = api.health().slice().sort((a, b) => a.port - b.port);
        list.textContent = '';
        svcs.forEach(s => {
          const card = api.el('div', 'card stat');
          const k = api.el('span', 'k');
          k.append(api.el('span', 'dot ' + s.state), document.createTextNode(s.role + ' · :' + s.port));
          const label = s.state === 'UP' ? 'Online' : s.state === 'DOWN' ? 'Offline' : 'Needs check';
          card.append(k, api.el('span', 'v', label), api.el('span', 'm', s.code ? 'HTTP ' + s.code + ' · ' + s.ms + 'ms' : 'no answer'));
          if (s.state !== 'UP') {
            const b = api.el('button', 'btn', 'Ask BlueBot why');
            b.onclick = () => api.ask('Service ' + s.role + ' on port ' + s.port + ' is ' + label +
              '. Read-only: inspect its log and process, report the cause, and propose the smallest fix. Do not restart anything.');
            card.append(b);
          }
          list.append(card);
        });
      }
      draw();
      api.every(15000, draw);
    }
  });
})();
