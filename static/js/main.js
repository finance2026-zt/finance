/* ═══════════════════════════════════════════════════════════════════════════
   MicroFinance LMS — Main Application JS
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
