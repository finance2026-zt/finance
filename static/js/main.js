/* ═══════════════════════════════════════════════════════════════════════════
   SGA Finance — Main Application JS
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Format a number as Indian Rupee string with ₹ prefix.
 * e.g. 123456.78  →  "₹1,23,456.78"
 */
function formatINR(amount) {
  return '₹' + parseFloat(amount).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Simple debounce function.
 */
function debounce(fn, wait) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}

// ── DOM Ready ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {

  // ── Sidebar toggle ──────────────────────────────────────────────────────
  const sidebar  = document.getElementById('sidebar');
  const content  = document.getElementById('content');
  const toggleBtn = document.getElementById('sidebarToggle');

  // Overlay element (created once)
  const overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  document.body.appendChild(overlay);

  function openSidebar() {
    sidebar?.classList.add('show');
    overlay.classList.add('show');
    document.body.style.overflow = 'hidden';
  }
  function closeSidebar() {
    sidebar?.classList.remove('show', 'collapsed');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
    content?.classList.remove('expanded');
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      const isMobile = window.innerWidth < 992;
      if (isMobile) {
        sidebar?.classList.contains('show') ? closeSidebar() : openSidebar();
      } else {
        sidebar?.classList.toggle('collapsed');
        content?.classList.toggle('expanded');
      }
    });
  }

  overlay.addEventListener('click', closeSidebar);

  // Close sidebar on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
  });

  // ── Auto-dismiss flash alerts after 6 s ────────────────────────────────
  setTimeout(() => {
    document.querySelectorAll('.alert.alert-dismissible').forEach(alert => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert.close();
    });
  }, 6000);

  // ── PAN number auto-uppercase ───────────────────────────────────────────
  document.querySelectorAll('[name="pan_number"], [name="bank_ifsc_code"]').forEach(el => {
    el.addEventListener('input', function () {
      const pos = this.selectionStart;
      this.value = this.value.toUpperCase();
      this.setSelectionRange(pos, pos);
    });
  });

  // ── Loan calculator (new_loan page) ────────────────────────────────────
  //    Watches principal / rate / duration inputs and calls the API preview
  const calcInputIds = ['principal_amount', 'interest_rate_percent', 'loan_duration_days'];
  calcInputIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', debounce(calculateLoanPreview, 450));
  });

  // ── Tooltips (Bootstrap data-bs-toggle="tooltip") ──────────────────────
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    bootstrap.Tooltip.getOrCreateInstance(el);
  });

  // ── Global form submit → loading button ──────────────────────────────
  //  On any <form> submit, the clicked submit button gets a spinner and is
  //  disabled so the user cannot double-click.
  //  Buttons with data-no-loading="true" are excluded.
  document.querySelectorAll('form').forEach(function (form) {
    // track which button triggered the submit
    form.querySelectorAll('[type="submit"]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        form._submitBtn = btn;
      });
    });

    form.addEventListener('submit', function () {
      const btn = form._submitBtn ||
                  form.querySelector('[type="submit"]');
      if (!btn || btn.dataset.noLoading === 'true') return;

      // Save original content and replace with spinner
      const originalHTML = btn.innerHTML;
      btn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' +
        'Please wait…';
      btn.disabled = true;
      btn.classList.add('btn-loading');

      // Safety fallback: re-enable after 15 s in case navigation stalls
      setTimeout(function () {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
        btn.classList.remove('btn-loading');
      }, 15000);
    });
  });

});

// ── Loan Calculation Preview ─────────────────────────────────────────────────

function calculateLoanPreview() {
  const principal = parseFloat(document.getElementById('principal_amount')?.value || 0);
  const rate      = parseFloat(document.getElementById('interest_rate_percent')?.value || 0);
  const days      = parseInt(document.getElementById('loan_duration_days')?.value || 0);

  if (!principal || !rate || !days || principal <= 0 || rate <= 0 || days <= 0) {
    document.getElementById('loan_preview')?.style.setProperty('display', 'none', '');
    return;
  }

  fetch('/api/calculate_loan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      principal_amount:      principal,
      interest_rate_percent: rate,
      loan_duration_days:    days,
    }),
  })
    .then(r => r.json())
    .then(res => {
      if (!res.success) return;
      const d = res.data;

      const set = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };

      set('preview_interest',   formatINR(d.total_interest_amount));
      set('preview_repayable',  formatINR(d.total_repayable_amount));
      set('preview_emi',        formatINR(d.daily_emi) + ' / day');

      // Due date preview
      const disbInput = document.querySelector('[name="disbursement_date"]');
      if (disbInput?.value) {
        const due = new Date(disbInput.value);
        due.setDate(due.getDate() + days);
        set('preview_due_date', due.toLocaleDateString('en-IN', {
          day: '2-digit', month: 'short', year: 'numeric',
        }));
      }

      // Penalty rate label
      const pRate = parseFloat(document.querySelector('[name="penalty_rate_percent"]')?.value || 1);
      set('preview_penalty_rate', pRate + '%');

      // Show the preview card
      const preview = document.getElementById('loan_preview');
      if (preview) preview.style.display = '';
    })
    .catch(err => console.error('[LoanCalc] Error:', err));
}

// ── Payment Modal ─────────────────────────────────────────────────────────────

/**
 * Called from templates: openPaymentModal(loanId, outstandingBalance)
 * Sets the form action and populates the balance display before opening.
 */
function openPaymentModal(loanId, balance) {
  const form = document.getElementById('paymentForm');
  const balDisplay = document.getElementById('currentBalanceDisplay');
  const amountInput = document.getElementById('paymentAmount');
  const notesInput  = document.getElementById('paymentNotes');

  if (form) {
    // Build action URL: works for both /user/loans/ and /admin paths
    const base = window.location.pathname.startsWith('/admin') ? '/user' : '';
    form.action = `/user/loans/${loanId}/collect`;
  }
  if (balDisplay) balDisplay.textContent = formatINR(balance);
  if (amountInput) { amountInput.value = ''; amountInput.focus(); }
  if (notesInput)   notesInput.value = '';

  const modalEl = document.getElementById('paymentModal');
  if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

// ── Confirm destructive actions ───────────────────────────────────────────────

function confirmAction(message, formOrCallback) {
  if (!confirm(message)) return false;
  if (typeof formOrCallback === 'function') formOrCallback();
  else if (formOrCallback instanceof HTMLFormElement) formOrCallback.submit();
  return true;
}

// ── Camera / Take Photo (admin new customer) ──────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const takeBtn = document.getElementById('takePhotoBtn');
  const photoInput = document.getElementById('photoInput');
  const preview = document.getElementById('photoPreview');
  const cameraModalEl = document.getElementById('cameraModal');
  if (!takeBtn || !photoInput || !cameraModalEl) return;

  const video = document.getElementById('cameraVideo');
  const canvas = document.getElementById('cameraCanvas');
  const captureBtn = document.getElementById('capturePhotoBtn');
  const switchBtn = document.getElementById('switchCameraBtn');
  const cameraModal = bootstrap.Modal.getOrCreateInstance(cameraModalEl);
  let stream = null;
  let facingMode = 'environment';

  async function startCamera() {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    try {
      const constraints = { video: { facingMode: facingMode }, audio: false };
      stream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      // Some browsers/devices may not support facingMode exact value — try fallback
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      } catch (err2) {
        console.error('[Camera] getUserMedia error:', err2 || err);
        throw err2 || err;
      }
    }
    video.srcObject = stream;
    await video.play();
  }

  takeBtn.addEventListener('click', async function () {
    cameraModal.show();
    try {
      await startCamera();
    } catch (err) {
      cameraModal.hide();
      alert('Unable to access camera: ' + (err.message || err));
    }
  });

  if (switchBtn) {
    switchBtn.addEventListener('click', async function () {
      // Toggle facing mode and restart camera if already open
      facingMode = (facingMode === 'environment') ? 'user' : 'environment';
      // Visual feedback (small flash) — optional
      switchBtn.classList.toggle('active');
      if (cameraModal._isShown) {
        try { await startCamera(); } catch (err) { console.warn('[Camera] switch error', err); }
      }
    });
  }

  captureBtn.addEventListener('click', function () {
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, w, h);
    canvas.toBlob(function (blob) {
      if (!blob) return;
      const filename = 'photo_' + Date.now() + '.jpg';
      try {
        const file = new File([blob], filename, { type: blob.type });
        const dt = new DataTransfer();
        dt.items.add(file);
        photoInput.files = dt.files;
        preview.src = URL.createObjectURL(blob);
        preview.style.display = '';
      } catch (e) {
        console.warn('[Camera] File/DataTransfer not supported, skipping attaching file', e);
      }
      cameraModal.hide();
      if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    }, 'image/jpeg', 0.95);
  });

  cameraModalEl.addEventListener('hidden.bs.modal', function () {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  });

  // Show preview when a file is chosen manually
  photoInput.addEventListener('change', function () {
    const f = (photoInput.files && photoInput.files[0]);
    if (!f) { preview.style.display = 'none'; preview.src = ''; return; }
    preview.src = URL.createObjectURL(f);
    preview.style.display = '';
  });
});
