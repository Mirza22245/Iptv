const state = { token: localStorage.getItem('lydia_token') };
const api = () => localStorage.getItem('lydia_api') || 'http://localhost:8000';
const $ = (id) => document.getElementById(id);

function message(text, error = false) {
  const el = $('message'); el.textContent = text; el.className = `notice${error ? ' error' : ''}`;
  el.classList.remove('hidden');
}
function clearMessage() { $('message').classList.add('hidden'); }
function showDashboard() {
  $('auth').classList.toggle('hidden', Boolean(state.token));
  $('dashboard').classList.toggle('hidden', !state.token);
  $('logout').classList.toggle('hidden', !state.token);
  if (state.token) loadBookings();
}
async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(`${api()}${path}`, { ...options, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

$('loginBtn').onclick = async () => {
  clearMessage();
  try {
    const body = await request('/api/auth/login', { method:'POST', body:JSON.stringify({ email:$('loginEmail').value, password:$('loginPassword').value }) });
    state.token = body.access_token; localStorage.setItem('lydia_token', state.token); showDashboard();
  } catch (e) { message(e.message, true); }
};

$('registerBtn').onclick = async () => {
  clearMessage();
  try {
    await request('/api/auth/register', { method:'POST', body:JSON.stringify({
      clinic_id:Number($('regClinic').value), first_name:$('regFirst').value, last_name:$('regLast').value,
      email:$('regEmail').value, password:$('regPassword').value
    })});
    message('Kontot skapades. Logga in med dina uppgifter.');
  } catch (e) { message(e.message, true); }
};

$('logout').onclick = () => { state.token = null; localStorage.removeItem('lydia_token'); showDashboard(); };

async function loadBookings() {
  const el = $('bookings');
  try {
    const rows = await request('/api/portal/bookings');
    if (!rows.length) { el.textContent = 'Inga bokningar ännu.'; return; }
    el.innerHTML = rows.map(b => `<div class="booking"><div><strong>${escapeHtml(b.service_name)}</strong> <span class="pill">${escapeHtml(b.status)}</span></div><div class="muted">${new Date(b.slot_start).toLocaleString('sv-SE')} · ${escapeHtml(b.staff_name)}</div><div style="margin-top:8px"><button class="danger" onclick="cancelBooking(${b.id})">Avboka</button></div></div>`).join('');
  } catch (e) { el.textContent = e.message; }
}
window.cancelBooking = async (id) => {
  try { await request(`/api/portal/bookings/${id}`, { method:'DELETE' }); message('Bokningen avbokades.'); loadBookings(); }
  catch (e) { message(e.message, true); }
};
$('bookBtn').onclick = async () => {
  clearMessage();
  try {
    const local = $('slotStart').value;
    if (!local) throw new Error('Välj en starttid.');
    await request('/api/portal/bookings', { method:'POST', body:JSON.stringify({ service_id:Number($('serviceId').value), staff_id:Number($('staffId').value), slot_start:new Date(local).toISOString() }) });
    message('Bokningen skapades.'); loadBookings();
  } catch (e) { message(e.message, true); }
};
function escapeHtml(v) { return String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
showDashboard();
