/* Public GitHub Pages demo mode. This is presentation-only and does not replace the real API. */
(() => {
  const accounts = {
    admin: { role: 'admin', id: 1, name: 'Lydia Admin', email: 'admin@lydia.local' },
    staff: { role: 'staff', id: 2, name: 'Lydia Personal', email: 'staff@lydia.local' },
    customer: { role: 'customer', id: 3, name: 'Demo Kund', email: 'customer@lydia.local' },
  };

  function enterDemo(kind) {
    const account = accounts[kind];
    state.token = `demo:${account.role}`;
    state.me = { id: account.id, clinic_id: 1, role: account.role, name: account.name, email: account.email };
    localStorage.setItem('lydia_token', state.token);
    localStorage.setItem('lydia_demo', '1');
    showDashboard();
    message('DEMO-LÄGE · GitHub Pages kör med testdata utan Lydia API.');
  }

  window.loadCustomerView = async () => {
    $('bookings').innerHTML = '<div class="booking"><strong>Ansiktsbehandling</strong> <span class="pill">Bekräftad</span><br><span class="muted">Idag 14:00 · Demo Personal</span></div><div class="booking"><strong>Konsultation</strong> <span class="pill">Bokad</span><br><span class="muted">Nästa vecka 10:30 · Demo Personal</span></div>';
    $('customerClinical').innerHTML = '<div class="card"><h2>Mitt kundkort</h2><p><strong>Demo Kund</strong></p><p class="muted">Samtycke registrerat · 1 journalanteckning</p></div>';
  };

  window.loadStaffView = async () => {
    $('staffBookings').innerHTML = '<div class="booking"><strong>14:00 · Demo Kund</strong><br>Ansiktsbehandling <span class="pill">Bekräftad</span></div><div class="booking"><strong>16:30 · Anna Demo</strong><br>Konsultation <span class="pill">Bokad</span></div>';
    $('staffCustomerPicker').innerHTML = '<option value="1">Demo Kund · customer@lydia.local</option><option value="2">Anna Demo · anna@lydia.local</option>';
  };

  window.loadAdminView = async () => {
    $('stats').innerHTML = [['Kunder','12'],['Personal','4'],['Aktiva tjänster','8'],['Bekräftade bokningar','27']].map(([label,value]) => `<div class="card"><div class="muted">${label}</div><div class="stat">${value}</div></div>`).join('');
    $('adminBookings').innerHTML = '<div class="booking"><strong>Idag 14:00</strong><br>Demo Kund · Ansiktsbehandling<br><span class="muted">Lydia Personal</span></div>';
    $('adminCustomers').innerHTML = '<div class="booking"><strong>Demo Kund</strong><br><span class="muted">customer@lydia.local · Aktiv</span></div><div class="booking"><strong>Anna Demo</strong><br><span class="muted">anna@lydia.local · Aktiv</span></div>';
    $('adminStaff').innerHTML = '<div class="booking"><strong>Lydia Personal</strong><br><span class="muted">staff@lydia.local · Aktiv</span></div>';
    $('adminServices').innerHTML = '<div class="booking"><strong>Ansiktsbehandling</strong><br><span class="muted">950 kr · 60 min · Aktiv</span></div><div class="booking"><strong>Konsultation</strong><br><span class="muted">500 kr · 30 min · Aktiv</span></div>';
    $('adminCustomerPicker').innerHTML = '<option value="1">Demo Kund · customer@lydia.local</option>';
  };

  window.addEventListener('DOMContentLoaded', () => {
    const auth = document.querySelector('#auth .card');
    if (!auth || document.getElementById('demoButtons')) return;
    const box = document.createElement('div');
    box.id = 'demoButtons';
    box.style.marginTop = '18px';
    box.innerHTML = '<div class="muted" style="margin-bottom:8px">Publikt demo – välj roll</div><div class="row"><button id="demoAdmin">Admin</button><button id="demoStaff" class="secondary">Personal</button><button id="demoCustomer" class="secondary">Kund</button></div>';
    auth.appendChild(box);
    $('demoAdmin').onclick = () => enterDemo('admin');
    $('demoStaff').onclick = () => enterDemo('staff');
    $('demoCustomer').onclick = () => enterDemo('customer');
  });
})();
