const state = {
  token: localStorage.getItem('lydia_token'),
  me: null,
};
const api = () => localStorage.getItem('lydia_api') || 'http://localhost:8000';
const $ = (id) => document.getElementById(id);

function message(text, error = false) {
  const el = $('message');
  el.textContent = String(text);
  el.className = `notice${error ? ' error' : ''}`;
  el.classList.remove('hidden');
}
function clearMessage() { $('message').classList.add('hidden'); }
function errorDetail(body, status) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || item?.detail || JSON.stringify(item)).join(', ');
  if (detail && typeof detail === 'object') return detail.message || detail.error || JSON.stringify(detail);
  return body?.message || `HTTP ${status}`;
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let res;
  try {
    res = await fetch(`${api()}${path}`, { ...options, headers });
  } catch (e) {
    throw new Error(`Kunde inte ansluta till Lydia API på ${api()}. Starta "Lydia Local.command".`, { cause: e });
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorDetail(body, res.status));
  return body;
}

function showDashboard() {
  const loggedIn = Boolean(state.token && state.me);
  $('auth').classList.toggle('hidden', loggedIn);
  $('dashboard').classList.toggle('hidden', !loggedIn);
  $('logout').classList.toggle('hidden', !loggedIn);
  if (!loggedIn) return;

  const role = state.me.role;
  $('customerView').classList.toggle('hidden', role !== 'customer');
  $('staffView').classList.toggle('hidden', role !== 'staff');
  $('adminView').classList.toggle('hidden', !['admin', 'superadmin'].includes(role));
  $('subtitle').textContent = `${roleLabel(role)} · klinik ${state.me.clinic_id}`;

  if (role === 'customer') loadCustomerView();
  if (role === 'staff') loadStaffView();
  if (role === 'admin' || role === 'superadmin') loadAdminView();
}

function roleLabel(role) {
  return ({ customer: 'Kundportal', staff: 'Personalportal', admin: 'Adminpanel', superadmin: 'Superadmin' })[role] || 'Dashboard';
}

async function loadSession() {
  if (!state.token) { showDashboard(); return; }
  try {
    state.me = await request('/api/dashboard/me');
    showDashboard();
  } catch (e) {
    state.token = null;
    state.me = null;
    localStorage.removeItem('lydia_token');
    showDashboard();
    message('Din session har gått ut. Logga in igen.', true);
  }
}

$('loginBtn').onclick = async () => {
  clearMessage();
  try {
    const body = await request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: $('loginEmail').value.trim(), password: $('loginPassword').value }),
    });
    state.token = body.access_token;
    localStorage.setItem('lydia_token', state.token);
    await loadSession();
  } catch (e) { message(e.message || String(e), true); }
};

$('registerBtn').onclick = async () => {
  clearMessage();
  try {
    await request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        clinic_id: Number($('regClinic').value),
        first_name: $('regFirst').value,
        last_name: $('regLast').value,
        email: $('regEmail').value.trim(),
        password: $('regPassword').value,
      }),
    });
    message('Kundkontot skapades. Logga in med dina uppgifter.');
  } catch (e) { message(e.message || String(e), true); }
};

$('logout').onclick = () => {
  state.token = null;
  state.me = null;
  localStorage.removeItem('lydia_token');
  clearMessage();
  showDashboard();
};

async function loadCustomerView() {
  const el = $('bookings');
  try {
    const rows = await request('/api/portal/bookings');
    if (!rows.length) { el.textContent = 'Inga bokningar ännu.'; return; }
    el.innerHTML = rows.map((b) => `<div class="booking"><div><strong>${escapeHtml(b.service_name)}</strong> <span class="pill">${escapeHtml(b.status)}</span></div><div class="muted">${new Date(b.slot_start).toLocaleString('sv-SE')} · ${escapeHtml(b.staff_name)}</div><div style="margin-top:8px"><button class="danger" onclick="cancelBooking(${b.id})">Avboka</button></div></div>`).join('');
  } catch (e) { el.textContent = e.message || String(e); }
}

window.cancelBooking = async (id) => {
  try {
    await request(`/api/portal/bookings/${id}`, { method: 'DELETE' });
    message('Bokningen avbokades.');
    loadCustomerView();
  } catch (e) { message(e.message || String(e), true); }
};

$('bookBtn').onclick = async () => {
  clearMessage();
  try {
    const local = $('slotStart').value;
    if (!local) throw new Error('Välj en starttid.');
    await request('/api/portal/bookings', {
      method: 'POST',
      body: JSON.stringify({
        service_id: Number($('serviceId').value),
        staff_id: Number($('staffId').value),
        slot_start: new Date(local).toISOString(),
      }),
    });
    message('Bokningen skapades.');
    loadCustomerView();
  } catch (e) { message(e.message || String(e), true); }
};

async function loadStaffView() {
  const el = $('staffBookings');
  try {
    const rows = await request('/api/dashboard/staff/today');
    if (!rows.length) { el.textContent = 'Inga bokningar idag.'; return; }
    el.innerHTML = `<div class="table-wrap"><table class="table"><thead><tr><th>Tid</th><th>Kund</th><th>Behandling</th><th>Status</th></tr></thead><tbody>${rows.map((b) => `<tr><td>${new Date(b.slot_start).toLocaleTimeString('sv-SE',{hour:'2-digit',minute:'2-digit'})}</td><td>${escapeHtml(b.customer_name)}<br><span class="muted">${escapeHtml(b.customer_email)}</span></td><td>${escapeHtml(b.service_name)}</td><td><span class="pill">${escapeHtml(b.status)}</span></td></tr>`).join('')}</tbody></table></div>`;
  } catch (e) { el.textContent = e.message || String(e); }
}

async function loadAdminView() {
  try {
    const [overview, customers, staff, services] = await Promise.all([
      request('/api/dashboard/admin/overview'),
      request('/api/dashboard/admin/customers'),
      request('/api/dashboard/admin/staff'),
      request('/api/dashboard/admin/services'),
    ]);
    $('stats').innerHTML = [
      ['Kunder', overview.counts.customers],
      ['Personal', overview.counts.staff],
      ['Aktiva tjänster', overview.counts.services],
      ['Bekräftade bokningar', overview.counts.confirmed_bookings],
    ].map(([label, value]) => `<div class="card"><div class="muted">${label}</div><div class="stat">${value}</div></div>`).join('');

    $('adminBookings').innerHTML = overview.upcoming.length
      ? overview.upcoming.map((b) => `<div class="booking"><strong>${new Date(b.slot_start).toLocaleString('sv-SE')}</strong><br>${escapeHtml(b.customer_name)} · ${escapeHtml(b.service_name)}<br><span class="muted">${escapeHtml(b.staff_name)}</span></div>`).join('')
      : 'Inga kommande bokningar.';

    $('adminCustomers').innerHTML = customers.length
      ? `<div class="table-wrap"><table class="table"><thead><tr><th>Namn</th><th>E-post</th><th>Status</th></tr></thead><tbody>${customers.map((c) => `<tr><td>${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</td><td>${escapeHtml(c.email)}</td><td>${c.is_active ? 'Aktiv' : 'Inaktiv'}</td></tr>`).join('')}</tbody></table></div>`
      : 'Inga kunder ännu.';

    $('adminStaff').innerHTML = staff.length
      ? staff.map((s) => `<div class="booking"><strong>${escapeHtml(s.display_name)}</strong><br><span class="muted">${escapeHtml(s.email)} · ${s.is_active ? 'Aktiv' : 'Inaktiv'}</span></div>`).join('')
      : 'Ingen personal ännu.';

    $('adminServices').innerHTML = services.length
      ? services.map((s) => `<div class="booking"><strong>${escapeHtml(s.name)}</strong><br><span class="muted">${Number(s.price).toFixed(2)} kr · ${s.duration_minutes} min · ${s.is_active ? 'Aktiv' : 'Inaktiv'}</span></div>`).join('')
      : 'Inga tjänster ännu.';
  } catch (e) {
    message(e.message || String(e), true);
  }
}

function escapeHtml(v) {
  return String(v).replace(/[&<>'"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[c]));
}

loadSession();
