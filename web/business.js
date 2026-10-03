(() => {
  const api = (window.lydiaApi || (async (path, options = {}) => {
    const token = localStorage.getItem('lydia_token');
    const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) };
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) { window.location.reload(); return null; }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || 'API-fel');
    return body;
  }));

  function getRoot() {
    return [...document.querySelectorAll('#businessWorkspace')].find(el => !el.closest('.hidden')) || document.querySelector('#businessWorkspace');
  }

  window.loadBusinessWorkspace = async function () {
    const root = getRoot();
    if (!root) return;
    root.innerHTML = `<div class="card"><h2>Kassa & Lager</h2><div class="grid"><div><h3>Produkter</h3><div id="businessProducts" class="muted">Laddar…</div></div><div><h3>Rapport idag</h3><div id="businessReport" class="muted">Laddar…</div></div></div><div style="margin-top:18px"><h3>Integrationer</h3><div id="businessIntegrations" class="muted">Laddar…</div></div></div>`;
    try {
      const [products, dashboard, integrations] = await Promise.all([api('/api/business/products'), api('/api/business/reports/dashboard'), api('/api/business/integrations')]);
      root.querySelector('#businessProducts').innerHTML = products.length ? products.map(p => `<div class="booking"><strong>${escapeHtml(p.name)}</strong> <span class="pill">${escapeHtml(p.sku)}</span><br><span class="muted">${p.stock_quantity} i lager · ${p.unit_price} kr</span></div>`).join('') : '<span class="muted">Inga produkter.</span>';
      root.querySelector('#businessReport').innerHTML = `<div class="stat">${dashboard.today.revenue} kr</div><div class="muted">${dashboard.today.sales_count} betalda köp idag</div>${dashboard.low_stock.length ? `<p class="notice">Lågt lager: ${dashboard.low_stock.map(x => escapeHtml(x.name)).join(', ')}</p>` : '<p class="muted">Inga låglagerprodukter.</p>'}`;
      root.querySelector('#businessIntegrations').innerHTML = integrations.length ? integrations.map(i => `<div class="booking"><strong>${escapeHtml(i.provider)}</strong> <span class="pill">${escapeHtml(i.status)}</span><br><span class="muted">Senaste synk: ${i.last_sync_at ? new Date(i.last_sync_at).toLocaleString('sv-SE') : 'inte synkad'}</span></div>`).join('') : '<span class="muted">Inga integrationer konfigurerade.</span>';
    } catch (e) { root.innerHTML += `<div class="notice error">${escapeHtml(e.message)}</div>`; }
  };

  window.openBusinessWorkspace = function () {
    const root = getRoot();
    if (!root) return;
    root.classList.remove('hidden');
    loadBusinessWorkspace();
  };

  function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
})();
