/* ── Mobile navigation — hamburger toggle ──────────────────────
   Handles:
   • aria-expanded toggling on the hamburger button
   • Overlay (semi-transparent) — tap to close
   • Close menu when a nav link is tapped
   • Close menu on Escape key, return focus to hamburger
   ─────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  function initNav() {
    var btn  = document.querySelector('.hamburger');
    var menu = document.getElementById('navbar');
    if (!btn || !menu) return;

    // Create overlay element once
    var overlay = document.createElement('div');
    overlay.id = 'nav-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    document.body.appendChild(overlay);

    function openMenu() {
      menu.classList.add('show');
      btn.setAttribute('aria-expanded', 'true');
      overlay.classList.add('show');
    }

    function closeMenu() {
      menu.classList.remove('show');
      btn.setAttribute('aria-expanded', 'false');
      overlay.classList.remove('show');
    }

    btn.addEventListener('click', function () {
      if (menu.classList.contains('show')) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    // Tapping the overlay closes the menu
    overlay.addEventListener('click', closeMenu);

    // Tapping any nav link closes the menu
    menu.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', closeMenu);
    });

    // Escape key closes the menu and returns focus
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && menu.classList.contains('show')) {
        closeMenu();
        btn.focus();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNav);
  } else {
    initNav();
  }
})();
