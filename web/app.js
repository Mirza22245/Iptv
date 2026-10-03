const state = { token: localStorage.getItem('lydia_token') };
const api = () => localStorage.getItem('lydia_api') || 'http://localhost:8000';
const $ = (id) => document.getElementById(id);

function message(text, error = false) {
  const el = $('message'); el.textContent = String(text); el.className = `notice${error ? ' error' : ''}`;
  el.classList.remove('hidden');
}
function clearMessage() { $('message').classList.add('hidden'); }
function showDashboard() {
  $('auth').classList.toggle('hidden', Boolean(state.token));
  $('dashboard').classList.toggle('hidden', !state.token);
  $('logout').classList.toggle('hidden', !state.token);
  if (state.token) loadBookings();
}
function errorDetail(body, status) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || item?.detail || JSON.stringify(item)).join(', ');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.error || JSON.stringify(detail);
  }
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

$('loginBtn').onclick = async () => {
  clearMessage();
  try {
    const body = await request('/api/auth/login', { method:'POST', body:JSON.stringify({ email:$('loginEmail').value.trim(), password:$('loginPassword').value }) });
    state.token = body.access_token;
    localStorage.setItem('lydia_token', state.token);
    showDashboard();
  } catch (e) { message(e.message || String(e), true); }
};

$('registerBtn').onclick = async () => {
  clearMessage();
  try {
    await request('/api/auth/register', { method:'POST', body:JSON.stringify({
      clinic_id:Number($('regClinic').value), first_name:$('regFirst').value, last_name:$('regLast').value,
      email:$('regEmail').value.trim(), password:$('regPassword').value
    })});
    message('Kontot skapades. Logga in med dina uppgifter.');
  } catch (e) { message(e.message || String(e), true); }
};

$('logout').onclick = () => { state.token = null; localStorage.removeItem('lydia_token'); showDashboard(); };

async function loadBookings() {
  const el = $('bookings');
  try {
    const rows = await request('/api/portal/bookings');
    if (!rows.length) { el.textContent = 'Inga bokningar ännu.'; return; }
    el.innerHTML = rows.map(b => `<div class="booking"><div><strong>${escapeHtml(b.service_name)}</strong> <span class="pill">${escapeHtml(b.status)}</span></div><div class="muted">${new Date(b.slot_start).toLocaleString('sv-SE')} · ${escapeHtml(b.staff_name)}</div><div style="margin-top:8px"><button class="danger" onclick="cancelBooking(${b.id})">Avboka</button></div></div>`).join('');
  } catch (e) { el.textContent = e.message || String(e); }
}
window.cancelBooking = async (id) => {
  try { await request(`/api/portal/bookings/${id}`, { method:'DELETE' }); message('Bokningen avbokades.'); loadBookings(); }
  catch (e) { message(e.message || String(e), true); }
};
$('bookBtn').onclick = async () => {
  clearMessage();
  try {
    const local = $('slotStart').value;
    if (!local) throw new Error('Välj en starttid.');
    await request('/api/portal/bookings', { method:'POST', body:JSON.stringify({ service_id:Number($('serviceId').value), staff_id:Number($('staffId').value), slot_start:new Date(local).toISOString() }) });
    message('Bokningen skapades.'); loadBookings();
  } catch (e) { message(e.message || String(e), true); }
};
function escapeHtml(v) { return String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
showDashboard();
