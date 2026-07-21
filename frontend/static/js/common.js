/**
 * CineBook   — common.js
 * Handles: JWT auth state, navbar rendering, toast notifications,
 *          seat booking with showtime context, active nav link.
 */

/* ═══════════════════════════════════════════════════════════════
   AUTH HELPERS
   ═══════════════════════════════════════════════════════════════ */

const Auth = {
  getToken  : ()       => localStorage.getItem('cb_token'),
  getUser   : ()       => localStorage.getItem('cb_username'),
  getRole   : ()       => localStorage.getItem('cb_role'),
  isAdmin   : ()       => localStorage.getItem('cb_role') === 'admin',
  isLoggedIn: ()       => !!localStorage.getItem('cb_token'),

  save(token, username, role) {
    localStorage.setItem('cb_token',    token);
    localStorage.setItem('cb_username', username);
    localStorage.setItem('cb_role',     role);
  },

  clear() {
    localStorage.removeItem('cb_token');
    localStorage.removeItem('cb_username');
    localStorage.removeItem('cb_role');
  },

  headers() {
    const t = this.getToken();
    return t ? { 'Authorization': `Bearer ${t}`, 'Content-Type': 'application/json' }
             : { 'Content-Type': 'application/json' };
  }
};

/* ─── Authenticated fetch wrapper ───────────────────────────── */
async function apiFetch(url, options = {}) {
  options.headers = { ...Auth.headers(), ...(options.headers || {}) };
  const res = await fetch(url, options);
  if (res.status === 401) {
    Auth.clear();
    window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
    return null;
  }
  return res;
}

/* ═══════════════════════════════════════════════════════════════
   NAVBAR — dynamic auth state
   ═══════════════════════════════════════════════════════════════ */
(function renderNavbar() {
  const authZone = document.getElementById('nav-auth-zone');
  const navLinksContainer = document.getElementById('nav-links-container');
  if (!authZone) return;

  const isLoggedIn = Auth.isLoggedIn();
  const isAdmin = isLoggedIn && Auth.isAdmin();

  if (navLinksContainer) {
    if (isAdmin) {
      navLinksContainer.innerHTML = '';
    } else {
      navLinksContainer.innerHTML = `
        <li class="nav-item"><a class="nav-link" href="/">Home</a></li>
        <li class="nav-item"><a class="nav-link" href="/movies.html">Movies</a></li>
        <li class="nav-item"><a class="nav-link nav-highlight" href="/booking.html">Book Tickets</a></li>
        <li class="nav-item"><a class="nav-link" href="/about.html">About</a></li>
        <li class="nav-item"><a class="nav-link" href="/faq.html">FAQ</a></li>
        <li class="nav-item"><a class="nav-link" href="/contact.html">Contact</a></li>
      `;
    }
  }

  if (isLoggedIn) {
    authZone.innerHTML = `
      <li class="nav-item">
        <span class="nav-user-pill ${isAdmin ? 'admin-pill' : ''}">
          <i class="fa-solid fa-circle-user"></i>
          ${Auth.getUser()}
          <span class="role-badge">${Auth.getRole()}</span>
        </span>
      </li>
      ${isAdmin
        ? `<li class="nav-item"><a class="nav-link" href="/admin"><i class="fa-solid fa-shield-halved me-1"></i>Admin</a></li>`
        : `<li class="nav-item"><a class="nav-link" href="/dashboard"><i class="fa-solid fa-ticket me-1"></i>My Tickets</a></li>`
      }
      <li class="nav-item">
        <button class="btn btn-outline-accent btn-sm ms-lg-2" onclick="logOut()">
          <i class="fa-solid fa-right-from-bracket me-1"></i>Sign Out
        </button>
      </li>`;
  } else {
    authZone.innerHTML = `
      <li class="nav-item ms-lg-3"><a class="btn btn-outline-accent" href="/login">Sign In</a></li>
      <li class="nav-item"><a class="btn btn-accent" href="/register">Join Free</a></li>`;
  }
})();

function logOut() {
  Auth.clear();
  window.location.href = '/';
}

/* ─── Active nav link   ────── */
(function () {
  const path = window.location.pathname.replace(/\/$/, '') || '/';
  document.querySelectorAll('.nav-link').forEach(link => {
    const href = (link.getAttribute('href') || '').replace(/\/$/, '') || '/';
    if (href === path) link.classList.add('active');
  });
})();

/* ─── Sync Admin Navbar Active State ──────────────────────────── */
function syncAdminNavbar(tabName) {
  // No-op: top navbar admin links have been removed to prevent duplicate navigation
}

/* ═══════════════════════════════════════════════════════════════
   TOAST
   ═══════════════════════════════════════════════════════════════ */
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const icon = type === 'success' ? 'fa-circle-check' : 'fa-circle-xmark';
  const id   = 'toast-' + Date.now();
  container.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="toast cb-toast ${type} show align-items-center mb-2" role="alert">
      <div class="d-flex align-items-center gap-3 p-3">
        <i class="fa-solid ${icon} toast-icon"></i>
        <div class="toast-body p-0">${message}</div>
        <button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>`);

  const el = document.getElementById(id);
  new bootstrap.Toast(el, { delay: 5000 }).show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

/* ═══════════════════════════════════════════════════════════════
   SEAT MAP RENDERER  ( : uses is_booked / seat_label)
   ═══════════════════════════════════════════════════════════════ */
function renderSeatMap(container, seats, onSeatClick) {
  if (!container || !seats) return;

  const rows = {};
  seats.forEach(s => {
    if (!rows[s.row]) rows[s.row] = [];
    rows[s.row].push(s);
  });

  container.innerHTML = '';
  Object.keys(rows).sort().forEach(rowLabel => {
    const rowDiv = document.createElement('div');
    rowDiv.className = 'd-flex align-items-center gap-2 mb-3 justify-content-center';

    const lbl = document.createElement('div');
    lbl.className = 'seat-row-label';
    lbl.textContent = rowLabel;
    rowDiv.appendChild(lbl);

    rows[rowLabel].forEach(seat => {
      const btn = document.createElement('button');
      let stateClass = 'free book-btn';
      let title = `Seat ${seat.seat_label} — Available`;
      let disabled = false;

      if (seat.is_booked) {
        stateClass = 'occupied';
        title = `Seat ${seat.seat_label} — Booked${seat.booked_by ? ' by ' + seat.booked_by : ''}`;
        disabled = true;
      } else if (seat.locked_by_me) {
        stateClass = 'selected';
        title = `Seat ${seat.seat_label} — Selected by you`;
      } else if (seat.is_locked) {
        stateClass = 'locked';
        title = `Seat ${seat.seat_label} — Being viewed by another user`;
      }

      btn.className = `seat-btn ${stateClass}`;
      btn.setAttribute('data-seat-num', seat.seat_number);
      btn.setAttribute('data-label',    seat.seat_label);
      btn.title = title;
      btn.disabled = disabled;
      btn.innerHTML = `<span>${seat.seat_label}</span>`;
      
      if (!disabled && onSeatClick) {
        btn.addEventListener('click', () => onSeatClick(seat, btn));
      }
      rowDiv.appendChild(btn);
    });

    container.appendChild(rowDiv);
  });
}

/* ═══════════════════════════════════════════════════════════════
   BOOKING FLOW HELPERS  (used on booking.html)
   ═══════════════════════════════════════════════════════════════ */

async function bookSeat(showtimeId, seatNumber, buttonEl) {
  if (!Auth.isLoggedIn()) {
    showToast('Please sign in to book a seat.', 'error');
    setTimeout(() => window.location.href = '/login', 1500);
    return;
  }

  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.classList.add('booking');
    buttonEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="font-size:.8rem"></i>';
  }

  try {
    const res  = await apiFetch(`/showtimes/${showtimeId}/book`, {
      method : 'POST',
      body   : JSON.stringify({ seat_number: seatNumber }),
    });
    if (!res) return;

    const data = await res.json();

    if (data.status === 'success') {
      showToast(`🎟️ ${data.message}`, 'success');
      if (buttonEl) {
        buttonEl.classList.remove('booking', 'free', 'book-btn');
        buttonEl.classList.add('occupied');
        buttonEl.innerHTML = `<i class="fa-solid fa-xmark" style="font-size:.7rem"></i>`;
        buttonEl.title = 'Occupied';
      }
      // Render ticket if on booking page
      if (data.ticket) renderTicketModal(data.ticket);
    } else {
      showToast(data.message || 'Booking failed.', 'error');
      if (buttonEl) {
        buttonEl.disabled = false;
        buttonEl.classList.remove('booking');
        buttonEl.innerHTML = `<span>${buttonEl.getAttribute('data-label')}</span>`;
      }
    }
  } catch (err) {
    showToast('Network error. Please try again.', 'error');
    if (buttonEl) {
      buttonEl.disabled = false;
      buttonEl.classList.remove('booking');
      buttonEl.innerHTML = `<span>${buttonEl.getAttribute('data-label')}</span>`;
    }
  }
}

/* ─── Ticket modal renderer ─────────────────────────────────── */
function renderTicketModal(ticket) {
  const overlay = document.getElementById('ticket-modal-overlay');
  const body    = document.getElementById('ticket-modal-body');
  if (!overlay || !body) return;

  const dt = new Date(ticket.show_timing);
  const dateStr = dt.toLocaleDateString('en-US', { weekday:'short', year:'numeric', month:'short', day:'numeric' });
  const timeStr = dt.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit' });

  body.innerHTML = `
    <div class="ticket-card mb-4">
      <div class="ticket-header d-flex justify-content-between align-items-start">
        <div>
          <div style="font-size:.65rem;color:var(--cb-muted);text-transform:uppercase;letter-spacing:.15em">Booking Confirmed</div>
          <div style="font-family:var(--cb-font-display);font-size:1.5rem;color:#fff;margin-top:2px">${ticket.movie_title}</div>
        </div>
        <div class="ticket-seat-badge">${ticket.seat_label}</div>
      </div>
      <div class="ticket-body">
        <div class="row g-3">
          <div class="col-6 ticket-field"><label>Hall</label><span>${ticket.hall_name}</span></div>
          <div class="col-6 ticket-field"><label>Date</label><span>${dateStr}</span></div>
          <div class="col-6 ticket-field"><label>Time</label><span>${timeStr}</span></div>
          <div class="col-6 ticket-field"><label>Seat</label><span>${ticket.seat_label} (${ticket.seat_number})</span></div>
          <div class="col-6 ticket-field"><label>Passenger</label><span>${ticket.passenger_name}</span></div>
          <div class="col-6 ticket-field"><label>Amount Paid</label><span>Rs. ${ticket.amount_paid.toFixed(2)}</span></div>
          <div class="col-12 ticket-field">
            <label>Transaction</label>
            <span style="font-family:monospace;font-size:.75rem;color:var(--cb-muted)">${ticket.transaction_id}</span>
          </div>
          <div class="col-12">
            <span class="ticket-status"><i class="fa-solid fa-circle-check"></i> Payment ${ticket.payment_status}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="d-flex gap-2">
      <button class="btn btn-accent flex-grow-1" onclick="document.getElementById('ticket-modal-overlay').classList.remove('open')">
        <i class="fa-solid fa-check me-2"></i>Done
      </button>
      <button class="btn btn-outline-accent" onclick="printReceipt('${encodeURIComponent(JSON.stringify(ticket))}')">
        <i class="fa-solid fa-print me-2"></i>Print Receipt
      </button>
    </div>`;

  overlay.classList.add('open');
}

/* ─── Print receipt helper ──────────────────────────────────── */
function printReceipt(ticketJsonEncoded) {
  const ticket = JSON.parse(decodeURIComponent(ticketJsonEncoded));
  const dt = new Date(ticket.show_timing);
  const dateStr = dt.toLocaleDateString('en-US', { weekday:'short', year:'numeric', month:'short', day:'numeric' });
  const timeStr = dt.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit' });
  
  const printWindow = window.open('', '_blank', 'width=600,height=700');
  printWindow.document.write(`
    <html>
      <head>
        <title>CineBook Receipt - Ticket #${ticket.ticket_id}</title>
        <style>
          body { font-family: 'DM Sans', Arial, sans-serif; color: #111; margin: 40px; line-height: 1.5; background: #fff; }
          .receipt-box { border: 2px solid #eee; padding: 30px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
          .header { text-align: center; border-bottom: 2px dashed #eee; padding-bottom: 20px; margin-bottom: 20px; }
          .header h2 { margin: 0; font-size: 24px; letter-spacing: 2px; }
          .header p { margin: 5px 0 0 0; color: #666; font-size: 14px; }
          .row { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 14px; }
          .row label { color: #666; font-weight: 500; }
          .row span { font-weight: bold; color: #111; }
          .total { border-top: 2px solid #111; border-bottom: 2px solid #111; padding: 15px 0; margin-top: 20px; font-size: 18px; font-weight: bold; }
          .footer { text-align: center; margin-top: 30px; font-size: 12px; color: #888; }
          .btn-print { display: block; width: 100%; text-align: center; background: #f5a623; color: #000; border: none; padding: 12px; font-weight: bold; cursor: pointer; border-radius: 5px; margin-top: 20px; text-transform: uppercase; font-size: 14px; }
          @media print {
            .btn-print { display: none; }
            body { margin: 20px; }
            .receipt-box { border: none; box-shadow: none; padding: 0; }
          }
        </style>
      </head>
      <body>
        <div class="receipt-box">
          <div class="header">
            <h2>CINEBOOK</h2>
            <p>Official Booking Receipt</p>
          </div>
          <div class="row"><label>Ticket ID</label><span>#${ticket.ticket_id}</span></div>
          <div class="row"><label>Movie</label><span>${ticket.movie_title}</span></div>
          <div class="row"><label>Hall</label><span>${ticket.hall_name}</span></div>
          <div class="row"><label>Date</label><span>${dateStr}</span></div>
          <div class="row"><label>Time</label><span>${timeStr}</span></div>
          <div class="row"><label>Seat Label</label><span>${ticket.seat_label} (Seat #${ticket.seat_number})</span></div>
          <div class="row"><label>Passenger</label><span>${ticket.passenger_name}</span></div>
          <div class="row"><label>Payment Status</label><span style="color: green;">${ticket.payment_status.toUpperCase()}</span></div>
          <div class="row"><label>Transaction ID</label><span style="font-family: monospace; font-size: 11px;">${ticket.transaction_id}</span></div>
          <div class="total">
            <div class="row" style="margin: 0;"><label style="color:#111;">TOTAL PAID</label><span>Rs. ${ticket.amount_paid.toFixed(2)}</span></div>
          </div>
          <div class="footer">
            <p>Thank you for choosing CineBook!</p>
            <p>Enjoy your movie!</p>
          </div>
          <button class="btn-print" onclick="window.print()">Print this Receipt</button>
        </div>
      </body>
    </html>
  `);
  printWindow.document.close();
}

/* ─── Format datetime   ────── */
function fmtDateTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
}
function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { weekday:'short', month:'short', day:'numeric', year:'numeric' });
}
function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit' });
}

/* ─── Seat Lock/Unlock API Helpers ───────────────────────────── */
async function lockSeat(showtimeId, seatNumber) {
  try {
    const res = await apiFetch(`/showtimes/${showtimeId}/lock`, {
      method: 'POST',
      body: JSON.stringify({ seat_number: seatNumber })
    });
    if (!res) return null;
    const data = await res.json();
    if (res.status !== 200) {
      showToast(data.detail || 'This seat is currently being viewed by another user. Please select a different seat or wait until it becomes available.', 'error');
      return null;
    }
    return data;
  } catch (err) {
    showToast('Network error locking seat.', 'error');
    return null;
  }
}

async function unlockSeat(showtimeId, seatNumber) {
  try {
    const res = await apiFetch(`/showtimes/${showtimeId}/unlock`, {
      method: 'POST',
      body: JSON.stringify({ seat_number: seatNumber })
    });
    if (!res) return null;
    return await res.json();
  } catch (err) {
    showToast('Network error releasing seat lock.', 'error');
    return null;
  }
}

async function unlockAllSeats(showtimeId) {
  try {
    const res = await apiFetch(`/showtimes/${showtimeId}/unlock-all`, {
      method: 'POST'
    });
    if (!res) return null;
    return await res.json();
  } catch (err) {
    console.error('Network error releasing all locks.', err);
    return null;
  }
}

/* ─── Receipt Printing   ────── */

async function printReceiptById(bookingId) {
  try {
    const res = await apiFetch(`/api/receipt/${bookingId}`);
    if (!res) return;
    const receipt = await res.json();
    if (res.status !== 200) {
      showToast(receipt.detail || 'Failed to retrieve receipt.', 'error');
      return;
    }
    
    const dt = new Date(receipt.show_timing);
    const dateStr = dt.toLocaleDateString('en-US', { weekday:'short', year:'numeric', month:'short', day:'numeric' });
    const timeStr = dt.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit' });
    
    const printWindow = window.open('', '_blank', 'width=600,height=700');
    printWindow.document.write(`
      <html>
        <head>
          <title>CineBook Receipt - Booking #${receipt.booking_id}</title>
          <style>
            body { font-family: 'DM Sans', Arial, sans-serif; color: #111; margin: 40px; line-height: 1.5; background: #fff; }
            .receipt-box { border: 2px solid #eee; padding: 30px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
            .header { text-align: center; border-bottom: 2px dashed #eee; padding-bottom: 20px; margin-bottom: 20px; }
            .header h2 { margin: 0; font-size: 24px; letter-spacing: 2px; }
            .header p { margin: 5px 0 0 0; color: #666; font-size: 14px; }
            .row { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 14px; }
            .row label { color: #666; font-weight: 500; }
            .row span { font-weight: bold; color: #111; }
            .total { border-top: 2px solid #111; border-bottom: 2px solid #111; padding: 15px 0; margin-top: 20px; font-size: 18px; font-weight: bold; }
            .footer { text-align: center; margin-top: 30px; font-size: 12px; color: #888; }
            .btn-print { display: block; width: 100%; text-align: center; background: #f5a623; color: #000; border: none; padding: 12px; font-weight: bold; cursor: pointer; border-radius: 5px; margin-top: 20px; text-transform: uppercase; font-size: 14px; }
            @media print {
              .btn-print { display: none; }
              body { margin: 20px; }
              .receipt-box { border: none; box-shadow: none; padding: 0; }
            }
          </style>
        </head>
        <body>
          <div class="receipt-box">
            <div class="header">
              <h2>CINEBOOK</h2>
              <p>Official Booking Receipt</p>
            </div>
            <div class="row"><label>Booking ID</label><span>#${receipt.booking_id}</span></div>
            <div class="row"><label>User Name</label><span>${receipt.username}</span></div>
            <div class="row"><label>Movie Name</label><span>${receipt.movie_title}</span></div>
            <div class="row"><label>Cinema Hall</label><span>${receipt.hall_name}</span></div>
            <div class="row"><label>Show Date & Time</label><span>${dateStr} at ${timeStr}</span></div>
            <div class="row"><label>Selected Seats</label><span>${receipt.selected_seats}</span></div>
            <div class="row"><label>Number of Tickets</label><span>${receipt.number_of_tickets}</span></div>
            <div class="row"><label>Payment Status</label><span style="color: green;">${receipt.payment_status.toUpperCase()}</span></div>
            <div class="row"><label>Booking Date & Time</label><span>${new Date(receipt.booking_date).toLocaleString()}</span></div>
            <div class="row"><label>Transaction ID</label><span style="font-family: monospace; font-size: 11px;">${receipt.transaction_id}</span></div>
            <div class="total">
              <div class="row" style="margin: 0;"><label style="color:#111;">TOTAL AMOUNT</label><span>Rs. ${receipt.total_amount.toFixed(2)}</span></div>
            </div>
            <div class="footer">
              <p>Thank you for choosing CineBook!</p>
              <p>Enjoy your movie!</p>
            </div>
            <button class="btn-print" onclick="window.print()">Print this Receipt</button>
          </div>
        </body>
      </html>
    `);
    printWindow.document.close();
  } catch (err) {
    console.error(err);
    showToast('Failed to print receipt.', 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════
   THEME TOGGLE SYSTEM
   ═══════════════════════════════════════════════════════════════ */
(function setupThemeToggle() {
  const toggleBtn = document.getElementById('theme-toggle');
  if (!toggleBtn) return;

  function updateIcon(theme) {
    const icon = toggleBtn.querySelector('i');
    if (!icon) return;
    if (theme === 'light') {
      icon.className = 'fa-solid fa-sun';
    } else {
      icon.className = 'fa-solid fa-moon';
    }
  }

  // Initialize icon on page load
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  updateIcon(currentTheme);

  toggleBtn.addEventListener('click', () => {
    const activeTheme = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', activeTheme);
    localStorage.setItem('cb_theme', activeTheme);
    updateIcon(activeTheme);
  });
})();
