// Splash screen controller — receives IPC events from the preload bridge.
// No Node.js APIs here; communication goes through contextBridge.

(function () {
  const statusEl = document.getElementById('status');
  const progressBar = document.getElementById('progressBar');
  const versionEl = document.getElementById('version');

  // Receive runtime:status updates
  if (window.leagent?.runtime?.onStatus) {
    window.leagent.runtime.onStatus((status) => {
      if (statusEl) statusEl.textContent = status;
    });
  }

  // Receive runtime:progress updates
  if (window.leagent?.runtime?.onProgress) {
    window.leagent.runtime.onProgress((data) => {
      if (progressBar) {
        progressBar.style.width = Math.min(100, Math.max(0, data.percent)) + '%';
      }
      if (data.detail && statusEl) {
        statusEl.textContent = data.detail;
      }
    });
  }

  // Set version from the bridge (async — contextBridge cannot expose sync version)
  if (window.leagent?.app?.getVersion && versionEl) {
    window.leagent.app.getVersion().then((v) => {
      if (v) versionEl.textContent = 'v' + v;
    }).catch(() => { /* keep placeholder */ });
  }

  // Simulate initial progress if no bridge (dev/testing)
  if (!window.leagent) {
    let pct = 0;
    const msgs = [
      'Initializing…',
      'Checking runtime…',
      'Starting backend…',
      'Awaiting health check…',
    ];
    const interval = setInterval(() => {
      pct += 2;
      if (progressBar) progressBar.style.width = Math.min(pct, 95) + '%';
      if (statusEl && pct % 25 === 0) {
        statusEl.textContent = msgs[Math.min(Math.floor(pct / 25), msgs.length - 1)];
      }
      if (pct >= 100) clearInterval(interval);
    }, 100);
  }
})();
