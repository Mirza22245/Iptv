async function clinicalUpload(path, formData) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(`${api()}${path}`, { method: 'POST', headers, body: formData });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorDetail(body, response.status));
  return body;
}

window.openImageForm = () => {
  const el = $('clinicalForm');
  if (!el) return;
  el.classList.remove('hidden');
  el.innerHTML = `<div class="clinical-form"><h3>Lägg till före-/efterbild</h3><label>Typ</label><select id="uploadType"><option value="before">Före</option><option value="after">Efter</option></select><label>Område</label><input id="uploadArea" placeholder="Ex. panna, kinder, läppar"><label>Bild</label><input id="uploadFile" type="file" accept="image/jpeg,image/png,image/webp"><div class="row" style="margin-top:14px"><button onclick="uploadClinicalImage()">Ladda upp säkert</button><button class="secondary" onclick="$('clinicalForm').classList.add('hidden')">Avbryt</button></div><p class="muted">Tillåtna format: JPEG, PNG och WebP. Max 10 MB.</p></div>`;
};

window.uploadClinicalImage = async () => {
  const file = $('uploadFile')?.files?.[0];
  if (!file) { message('Välj en bild först.', true); return; }
  if (file.size > 10 * 1024 * 1024) { message('Bilden är större än 10 MB.', true); return; }
  try {
    const form = new FormData();
    form.append('image_type', $('uploadType').value);
    form.append('area', $('uploadArea').value);
    form.append('file', file);
    await clinicalUpload(`/api/clinical/customers/${state.clinicalCustomerId}/images/upload`, form);
    message('Bilden laddades upp och kopplades till kundkortet.');
    await renderClinicalCard(state.clinicalCustomerId, state.me.role === 'customer' ? 'customerClinical' : 'clinicalWorkspace');
  } catch (e) { message(e.message, true); }
};
