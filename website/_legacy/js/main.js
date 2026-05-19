(function () {
  'use strict';

  var STORAGE_KEY = 'leagent-site-theme';
  var mqDark = window.matchMedia('(prefers-color-scheme: dark)');

  function getStoredTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (_) {
      return null;
    }
  }

  function setStoredTheme(value) {
    try {
      if (value) localStorage.setItem(STORAGE_KEY, value);
      else localStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
  }

  function applyTheme(theme) {
    var root = document.documentElement;
    if (theme === 'dark') root.classList.add('dark');
    else if (theme === 'light') root.classList.remove('dark');
    else {
      if (mqDark.matches) root.classList.add('dark');
      else root.classList.remove('dark');
    }

    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute(
        'content',
        root.classList.contains('dark') ? '#09090a' : '#fcfcf9'
      );
    }

    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      var dark = root.classList.contains('dark');
      toggle.setAttribute('aria-label', dark ? '切换到浅色主题' : '切换到深色主题');
      toggle.setAttribute('aria-pressed', dark ? 'true' : 'false');
    }
  }

  function resolveTheme() {
    var stored = getStoredTheme();
    if (stored === 'dark' || stored === 'light') return stored;
    return 'system';
  }

  /** Initial paint — run before first paint if script is deferred */
  applyTheme(resolveTheme());

  document.addEventListener('DOMContentLoaded', function () {
    applyTheme(resolveTheme());

    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.addEventListener('click', function () {
        var root = document.documentElement;
        var next =
          root.classList.contains('dark') ? 'light' : 'dark';
        setStoredTheme(next);
        applyTheme(next);
      });
    }

    mqDark.addEventListener('change', function () {
      if (getStoredTheme()) return;
      applyTheme('system');
    });

    var navToggle = document.getElementById('nav-toggle');
    var navPanel = document.getElementById('nav-panel');
    if (navToggle && navPanel) {
      navToggle.addEventListener('click', function () {
        var open = navPanel.classList.toggle('is-open');
        navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      navPanel.querySelectorAll('a').forEach(function (a) {
        a.addEventListener('click', function () {
          navPanel.classList.remove('is-open');
          navToggle.setAttribute('aria-expanded', 'false');
        });
      });
    }

    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      var id = a.getAttribute('href').slice(1);
      if (!id) return;
      a.addEventListener('click', function (e) {
        var el = document.getElementById(id);
        if (!el) return;
        e.preventDefault();
        el.scrollIntoView({
          behavior: reduceMotion.matches ? 'auto' : 'smooth',
          block: 'start',
        });
        history.replaceState(null, '', '#' + id);
      });
    });

    document.querySelectorAll('[data-tabs]').forEach(function (container) {
      var buttons = container.querySelectorAll('.tablist__btn');
      var panels = container.querySelectorAll('.tab-panel');
      if (!buttons.length || !panels.length) return;

      buttons.forEach(function (btn) {
        btn.addEventListener('click', function () {
          var targetId = btn.getAttribute('data-tab-target');
          if (!targetId) return;

          buttons.forEach(function (b) {
            b.classList.remove('is-active');
            b.setAttribute('aria-selected', 'false');
          });
          btn.classList.add('is-active');
          btn.setAttribute('aria-selected', 'true');

          panels.forEach(function (p) {
            var on = p.id === targetId;
            p.classList.toggle('is-active', on);
            if (on) p.removeAttribute('hidden');
            else p.setAttribute('hidden', '');
          });
        });
      });
    });

    var reduceReveal = window.matchMedia(
      '(prefers-reduced-motion: reduce)'
    ).matches;
    var sections = document.querySelectorAll('main > section');
    var footerReveal = document.querySelector('.site-footer');

    sections.forEach(function (sec, i) {
      sec.classList.add('reveal-on-scroll');
      sec.style.setProperty('--reveal-delay', Math.min(i * 42, 280) + 'ms');
    });

    if (footerReveal) {
      footerReveal.classList.add('reveal-on-scroll');
      footerReveal.style.setProperty(
        '--reveal-delay',
        Math.min(sections.length * 42, 320) + 'ms'
      );
    }

    function reveal(el) {
      el.classList.add('is-revealed');
    }

    if (reduceReveal) {
      sections.forEach(function (sec) {
        reveal(sec);
      });
      if (footerReveal) reveal(footerReveal);
    } else if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            reveal(entry.target);
            io.unobserve(entry.target);
          });
        },
        {
          root: null,
          rootMargin: '90px 0px 80px 0px',
          threshold: 0,
        }
      );

      sections.forEach(function (sec) {
        io.observe(sec);
      });
      if (footerReveal) io.observe(footerReveal);
    } else {
      sections.forEach(function (sec) {
        reveal(sec);
      });
      if (footerReveal) reveal(footerReveal);
    }

    var header = document.querySelector('.site-header');
    var scrollThreshold = 12;
    var ticking = false;

    function updateHeaderScrolled() {
      ticking = false;
      if (!header) return;
      var y = window.scrollY || document.documentElement.scrollTop;
      header.classList.toggle('is-scrolled', y > scrollThreshold);
    }

    window.addEventListener(
      'scroll',
      function () {
        if (!header || ticking) return;
        ticking = true;
        window.requestAnimationFrame(updateHeaderScrolled);
      },
      { passive: true }
    );
    updateHeaderScrolled();
  });
})();
