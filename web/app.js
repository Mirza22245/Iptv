const state = {
  token: localStorage.getItem('lydia_token'),
  me: null,
  clinicalCustomerId: null,
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
    if (!rows.length) el.textContent = 'Inga bokningar ännu.';
    else el.innerHTML = rows.map((b) => `<div class="booking"><div><strong>${escapeHtml(b.service_name)}</strong> <span class="pill">${escapeHtml(b.status)}</span></div><div class="muted">${new Date(b.slot_start).toLocaleString('sv-SE')} · ${escapeHtml(b.staff_name)}</div><div style="margin-top:8px"><button class="danger" onclick="cancelBooking(${b.id})">Avboka</button></div></div>`).join('');

    const me = await request('/api/dashboard/me');
    const customer = await request(`/api/clinical/customers/${me.customer_id || me.id}`);
    state.clinicalCustomerId = customer.id;
    await renderClinicalCard(customer.id, 'customerClinical');
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
    if (!rows.length) el.textContent = 'Inga bokningar idag.';
    else el.innerHTML = `<div class="table-wrap"><table class="table"><thead><tr><th>Tid</th><th>Kund</th><th>Behandling</th><th>Status</th><th></th></tr></thead><tbody>${rows.map((b) => `<tr><td>${new Date(b.slot_start).toLocaleTimeString('sv-SE',{hour:'2-digit',minute:'2-digit'})}</td><td>${escapeHtml(b.customer_name)}<br><span class="muted">${escapeHtml(b.customer_email)}</span></td><td>${escapeHtml(b.service_name)}</td><td><span class="pill">${escapeHtml(b.status)}</span></td><td><button class="secondary" onclick="openClinicalCustomer(${b.customer_id})">Kundkort</button></td></tr>`).join('')}</tbody></table></div>`;
  } catch (e) { el.textContent = e.message || String(e); }
  await loadClinicalCustomerPicker('staffCustomerPicker');
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
      ? `<div class="table-wrap"><table class="table"><thead><tr><th>Namn</th><th>E-post</th><th>Status</th><th></th></tr></thead><tbody>${customers.map((c) => `<tr><td>${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</td><td>${escapeHtml(c.email)}</td><td>${c.is_active ? 'Aktiv' : 'Inaktiv'}</td><td><button class="secondary" onclick="openClinicalCustomer(${c.id})">Kundkort</button></td></tr>`).join('')}</tbody></table></div>`
      : 'Inga kunder ännu.';

    $('adminStaff').innerHTML = staff.length
      ? staff.map((s) => `<div class="booking"><strong>${escapeHtml(s.display_name)}</strong><br><span class="muted">${escapeHtml(s.email)} · ${s.is_active ? 'Aktiv' : 'Inaktiv'}</span></div>`).join('')
      : 'Ingen personal ännu.';

    $('adminServices').innerHTML = services.length
      ? services.map((s) => `<div class="booking"><strong>${escapeHtml(s.name)}</strong><br><span class="muted">${Number(s.price).toFixed(2)} kr · ${s.duration_minutes} min · ${s.is_active ? 'Aktiv' : 'Inaktiv'}</span></div>`).join('')
      : 'Inga tjänster ännu.';
  } catch (e) { message(e.message || String(e), true); }
  await loadClinicalCustomerPicker('adminCustomerPicker');
}

async function loadClinicalCustomerPicker(elementId) {
  const select = $(elementId);
  if (!select) return;
  try {
    const customers = await request('/api/clinical/customers');
    select.innerHTML = '<option value="">Välj kund…</option>' + customers.map((c) => `<option value="${c.id}">${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)} · ${escapeHtml(c.email || '')}</option>`).join('');
  } catch (e) { select.innerHTML = `<option value="">${escapeHtml(e.message)}</option>`; }
}

window.openClinicalFromPicker = async (elementId) => {
  const id = Number($(elementId)?.value);
  if (!id) return;
  await openClinicalCustomer(id);
};

window.openClinicalCustomer = async (customerId) => {
  state.clinicalCustomerId = Number(customerId);
  const target = $('clinicalWorkspace');
  if (!target) return;
  target.classList.remove('hidden');
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  await renderClinicalCard(state.clinicalCustomerId, 'clinicalWorkspace');
};

async function renderClinicalCard(customerId, targetId) {
  const target = $(targetId);
  if (!target) return;
  target.innerHTML = '<div class="card"><div class="muted">Laddar kundkort…</div></div>';
  try {
    const [customer, journals, consents, images, templates] = await Promise.all([
      request(`/api/clinical/customers/${customerId}`),
      request(`/api/clinical/customers/${customerId}/journals`),
      request(`/api/clinical/customers/${customerId}/consents`),
      request(`/api/clinical/customers/${customerId}/images`),
      state.me.role === 'customer' ? Promise.resolve([]) : request('/api/clinical/templates'),
    ]);
    const canWrite = ['staff','admin','superadmin'].includes(state.me.role);
    target.innerHTML = `
      <div class="card clinical-card">
        <div class="row" style="justify-content:space-between"><div><h2>Kundkort · ${escapeHtml(customer.first_name)} ${escapeHtml(customer.last_name)}</h2><div class="muted">${escapeHtml(customer.email || '')} · kund-ID ${customer.id}</div></div>${canWrite ? '<button onclick="openJournalForm()">+ Ny journal</button>' : ''}</div>
        <div class="clinical-grid" style="margin-top:18px">
          <div><h3>Journal</h3><div id="clinicalJournals">${renderJournals(journals, customer.id, canWrite)}</div></div>
          <div><h3>Samtycken</h3><div id="clinicalConsents">${renderConsents(consents)}</div>${canWrite ? '<button class="secondary" style="margin-top:10px" onclick="openConsentForm()">+ Registrera samtycke</button>' : ''}<h3 style="margin-top:24px">Före / efter</h3><div id="clinicalImages">${renderImages(images)}</div>${canWrite ? '<button class="secondary" style="margin-top:10px" onclick="openImageForm()">+ Lägg till bildmetadata</button>' : ''}</div>
        </div>
        ${canWrite ? `<div id="clinicalForm" class="hidden" style="margin-top:20px"></div>` : ''}
        ${canWrite ? `<div style="margin-top:24px"><h3>Journalmallar</h3><div class="muted">${templates.length ? templates.map((t) => `<span class="pill" style="margin:0 6px 6px 0;display:inline-block">${escapeHtml(t.title)}</span>`).join('') : 'Inga mallar ännu.'}</div></div>` : ''}
      </div>`;
  } catch (e) { target.innerHTML = `<div class="card"><div class="error notice">${escapeHtml(e.message)}</div></div>`; }
}

function renderJournals(rows, customerId, canWrite) {
  if (!rows.length) return '<div class="muted">Inga journalanteckningar ännu.</div>';
  return rows.map((j) => `<div class="clinical-item"><div class="row" style="justify-content:space-between"><strong>${escapeHtml(j.treatment || 'Journalanteckning')}</strong><span class="pill">${j.is_signed ? '🔒 Signerad' : 'Utkast'}</span></div><div class="muted" style="margin:6px 0">${new Date(j.created_at).toLocaleString('sv-SE')} · behandlare ${j.author_id}</div><p><strong>Bedömning:</strong> ${escapeHtml(j.assessment || '–')}</p><p><strong>Plan:</strong> ${escapeHtml(j.plan || '–')}</p>${j.products_used ? `<p><strong>Produkter:</strong> ${escapeHtml(j.products_used)}</p>` : ''}${j.result ? `<p><strong>Resultat:</strong> ${escapeHtml(j.result)}</p>` : ''}${canWrite && !j.is_signed ? `<div><button onclick="signClinicalJournal(${j.id},${customerId})">Signera & lås</button></div>` : ''}</div>`).join('');
}
function renderConsents(rows) {
  if (!rows.length) return '<div class="muted">Inga samtycken registrerade.</div>';
  return rows.map((c) => `<div class="clinical-item"><strong>${escapeHtml(c.title)}</strong><div class="muted">Version ${escapeHtml(c.version)} · ${new Date(c.signed_at).toLocaleString('sv-SE')}</div></div>`).join('');
}
function renderImages(rows) {
  if (!rows.length) return '<div class="muted">Inga före/efter-bilder registrerade.</div>';
  return rows.map((i) => `<div class="clinical-item"><div class="row" style="justify-content:space-between"><strong>${i.image_type === 'before' ? 'Före' : 'Efter'}</strong><span class="pill">${escapeHtml(i.area || 'Område ej angivet')}</span></div><div class="muted">${escapeHtml(i.file_path)}</div></div>`).join('');
}

window.openJournalForm = () => {
  const el = $('clinicalForm');
  if (!el) return;
  el.classList.remove('hidden');
  el.innerHTML = `<div class="clinical-form"><h3>Ny journalanteckning</h3><div class="grid"><div><label>Behandling</label><input id="jTreatment"><label>Område</label><input id="jArea"><label>Indikation</label><textarea id="jIndication"></textarea><label>Bedömning</label><textarea id="jAssessment"></textarea></div><div><label>Plan</label><textarea id="jPlan"></textarea><label>Produkter/material</label><input id="jProducts"><label>Dosering</label><input id="jDosage"><label>Lot/batch</label><input id="jLot"><label>Resultat</label><textarea id="jResult"></textarea><label>Komplikationer</label><textarea id="jComplications"></textarea><label>Eftervård</label><textarea id="jAftercare"></textarea></div></div><div class="row" style="margin-top:14px"><button onclick="saveClinicalJournal()">Spara utkast</button><button class="secondary" onclick="$('clinicalForm').classList.add('hidden')">Avbryt</button></div></div>`;
};

window.saveClinicalJournal = async () => {
  try {
    await request('/api/clinical/journals', { method: 'POST', body: JSON.stringify({ customer_id: state.clinicalCustomerId, treatment: $('jTreatment').value, area: $('jArea').value, indication: $('jIndication').value, assessment: $('jAssessment').value, plan: $('jPlan').value, products_used: $('jProducts').value, dosage: $('jDosage').value, lot_batch: $('jLot').value, result: $('jResult').value, complications: $('jComplications').value, aftercare: $('jAftercare').value }) });
    message('Journalutkast sparat.');
    await renderClinicalCard(state.clinicalCustomerId, 'clinicalWorkspace');
  } catch (e) { message(e.message, true); }
};

window.signClinicalJournal = async (journalId, customerId) => {
  if (!confirm('Signera journalen? En signerad journal blir permanent låst och kan inte ändras.')) return;
  try {
    await request(`/api/clinical/journals/${journalId}/sign`, { method: 'POST' });
    message('Journalen är signerad och låst.');
    await renderClinicalCard(customerId, state.me.role === 'customer' ? 'customerClinical' : 'clinicalWorkspace');
  } catch (e) { message(e.message, true); }
};

window.openConsentForm = () => {
  const el = $('clinicalForm');
  if (!el) return;
  el.classList.remove('hidden');
  el.innerHTML = `<div class="clinical-form"><h3>Registrera samtycke</h3><label>Titel</label><input id="cTitle" placeholder="Behandlingssamtycke"><label>Version</label><input id="cVersion" placeholder="1.0"><label>Signaturdata</label><textarea id="cSignature" placeholder="Intern signatur/hash"></textarea><div class="row" style="margin-top:14px"><button onclick="saveConsent()">Spara samtycke</button><button class="secondary" onclick="$('clinicalForm').classList.add('hidden')">Avbryt</button></div></div>`;
};
window.saveConsent = async () => {
  try {
    await request('/api/clinical/consents', { method: 'POST', body: JSON.stringify({ customer_id: state.clinicalCustomerId, title: $('cTitle').value, version: $('cVersion').value, signature_data: $('cSignature').value }) });
    message('Samtycket registrerades.');
    await renderClinicalCard(state.clinicalCustomerId, 'clinicalWorkspace');
  } catch (e) { message(e.message, true); }
};
window.openImageForm = () => {
  const el = $('clinicalForm');
  if (!el) return;
  el.classList.remove('hidden');
  el.innerHTML = `<div class="clinical-form"><h3>Lägg till före/efter-metadata</h3><label>Typ</label><select id="iType"><option value="before">Före</option><option value="after">Efter</option></select><label>Område</label><input id="iArea"><label>Filväg / lagrings-ID</label><input id="iPath" placeholder="Exempel: customer-12/before-2026-10-04.jpg"><div class="row" style="margin-top:14px"><button onclick="saveImageMetadata()">Spara</button><button class="secondary" onclick="$('clinicalForm').classList.add('hidden')">Avbryt</button></div><p class="muted">Detta registrerar metadata. Själva säkra filuppladdningen kopplas in i nästa media-steg.</p></div>`;
};
window.saveImageMetadata = async () => {
  try {
    await request('/api/clinical/images', { method: 'POST', body: JSON.stringify({ customer_id: state.clinicalCustomerId, image_type: $('iType').value, area: $('iArea').value, file_path: $('iPath').value }) });
    message('Bildmetadata registrerad.');
    await renderClinicalCard(state.clinicalCustomerId, 'clinicalWorkspace');
  } catch (e) { message(e.message, true); }
};

function escapeHtml(v) {
  return String(v).replace(/[&<>'"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[c]));
}

loadSession();
