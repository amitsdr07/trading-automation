(function() {
  const getKey = () => localStorage.getItem('apiKey') || '';
  const setKey = (k) => localStorage.setItem('apiKey', k || '');
  document.getElementById('saveKey').addEventListener('click', () => {
    const v = document.getElementById('apiKey').value;
    setKey(v);
    document.getElementById('status').textContent = v ? 'Saved' : 'Cleared';
    loadAll();
  });
  document.getElementById('apiKey').value = getKey();

  async function fetchJSON(path) {
    const headers = {};
    const k = getKey();
    if (k) headers['X-API-Key'] = k;
    const res = await fetch(path, { headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function loadEquity() {
    try {
      const data = await fetchJSON('/equity?limit=1000');
      const xs = data.map((d, i) => i);
      const ys = data.map(d => d.equity);
      const ctx = document.getElementById('equityChart').getContext('2d');
      if (window._eqChart) window._eqChart.destroy();
      window._eqChart = new Chart(ctx, {
        type: 'line',
        data: { labels: xs, datasets: [{ label: 'Equity', data: ys, fill: false }]},
        options: { responsive: false }
      });
    } catch (e) { console.error('equity', e); }
  }

  async function loadPositions() {
    try {
      const data = await fetchJSON('/positions');
      const tbody = document.querySelector('#positions tbody');
      tbody.innerHTML = '';
      data.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.symbol}</td><td>${r.side}</td><td>${r.qty}</td><td>${r.avg_price}</td><td>${r.ts}</td>`;
        tbody.appendChild(tr);
      });
    } catch (e) { console.error('positions', e); }
  }

  async function loadOrders() {
    try {
      const data = await fetchJSON('/orders?limit=200');
      const tbody = document.querySelector('#orders tbody');
      tbody.innerHTML = '';
      data.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.ts}</td><td>${r.symbol}</td><td>${r.side}</td><td>${r.qty}</td><td>${r.price}</td><td>${r.status}</td><td>${r.strategy || ''}</td>`;
        tbody.appendChild(tr);
      });
    } catch (e) { console.error('orders', e); }
  }

  async function loadLogs() {
    try {
      const data = await fetchJSON('/logs?limit=200');
      const tbody = document.querySelector('#logs tbody');
      tbody.innerHTML = '';
      data.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.ts}</td><td><pre>${r.data}</pre></td>`;
        tbody.appendChild(tr);
      });
    } catch (e) { console.error('logs', e); }
  }

  async function loadAll() {
    await Promise.all([loadEquity(), loadPositions(), loadOrders(), loadLogs()]);
  }

  loadAll();
  setInterval(loadAll, 10000);
})();
