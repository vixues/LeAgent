(function () {
  const subtitle = document.getElementById('subtitle');
  const checksEl = document.getElementById('checks');
  const logTail = document.getElementById('logTail');
  const statusEl = document.getElementById('status');
  const api = window.leagent;

  // Frameless window controls: native traffic lights (mac) / overlay (win) cover
  // this themselves; Linux ('custom') needs our own buttons to move/close.
  const titlebar = document.getElementById('titlebar');
  const winControls = document.getElementById('winControls');
  const style = api?.window?.style;
  if (style === 'mac' && titlebar) {
    titlebar.style.paddingLeft = '78px';
  }
  if (style === 'custom' && winControls) {
    winControls.hidden = false;
    document.getElementById('winMin')?.addEventListener('click', () => api?.window?.minimize?.());
    document.getElementById('winMax')?.addEventListener('click', () => api?.window?.maximizeToggle?.());
    document.getElementById('winClose')?.addEventListener('click', () => api?.window?.close?.());
  }

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  function renderChecks(result) {
    if (!checksEl || !result?.items) return;
    checksEl.innerHTML = '';
    for (const item of result.items) {
      const li = document.createElement('li');
      const badge = document.createElement('span');
      badge.className = 'badge ' + item.level;
      badge.textContent = item.level;
      const text = document.createElement('span');
      text.innerHTML = '<strong>' + item.label + '</strong>: ' + item.message;
      li.appendChild(badge);
      li.appendChild(text);
      checksEl.appendChild(li);
    }
    if (subtitle) {
      subtitle.textContent = result.ok
        ? 'All critical checks passed. You can retry launch.'
        : 'Some checks failed. Try a repair action below.';
    }
  }

  async function refreshValidation() {
    if (!api?.install?.validate) return;
    try {
      const result = await api.install.validate();
      renderChecks(result);
    } catch (e) {
      setStatus('Validation failed: ' + (e?.message || e));
    }
  }

  async function refreshDiagnostics() {
    if (!api?.app?.getDiagnostics) return;
    try {
      const diag = await api.app.getDiagnostics();
      if (logTail && Array.isArray(diag.recentBackendLogs)) {
        logTail.textContent = diag.recentBackendLogs.join('\n') || '(no backend logs yet)';
      }
    } catch {
      /* ignore */
    }
  }

  if (api?.server?.onLog && logTail) {
    api.server.onLog((line) => {
      logTail.textContent = (logTail.textContent + '\n' + line).trim().split('\n').slice(-200).join('\n');
    });
  }

  document.getElementById('btnReinstall')?.addEventListener('click', async () => {
    setStatus('Reinstalling…');
    const r = await api?.install?.repair?.('reinstall');
    setStatus(r?.ok ? 'Reinstall complete.' : r?.message || 'Reinstall failed.');
    await refreshValidation();
  });

  document.getElementById('btnUpgrade')?.addEventListener('click', async () => {
    setStatus('Syncing dependencies…');
    const r = await api?.install?.repair?.('upgrade');
    setStatus(r?.ok ? 'Sync complete.' : r?.message || 'Sync failed.');
    await refreshValidation();
  });

  document.getElementById('btnAlembic')?.addEventListener('click', async () => {
    setStatus('Running Alembic migrations…');
    const r = await api?.install?.repair?.('alembic');
    setStatus(r?.ok ? 'Migrations complete.' : r?.message || 'Migrations failed.');
    await refreshValidation();
  });

  document.getElementById('btnRestartServer')?.addEventListener('click', async () => {
    setStatus('Restarting backend…');
    const r = await api?.server?.restart?.();
    setStatus(r?.ok ? 'Backend restarted.' : r?.message || 'Restart failed.');
  });

  document.getElementById('btnOpenLogs')?.addEventListener('click', () => {
    api?.app?.openLogsDir?.();
  });

  document.getElementById('btnCopyDiag')?.addEventListener('click', async () => {
    const r = await api?.app?.copyDiagnostics?.();
    setStatus(r?.ok ? 'Diagnostics copied to clipboard.' : 'Copy failed.');
  });

  document.getElementById('btnRetry')?.addEventListener('click', async () => {
    setStatus('Retrying launch…');
    const r = await api?.install?.retryBoot?.();
    if (r?.ok) {
      setStatus('Launch succeeded.');
    } else {
      setStatus(r?.message || 'Launch failed — see checks above.');
      await refreshValidation();
    }
  });

  document.getElementById('btnForceApp')?.addEventListener('click', () => {
    api?.app?.openApp?.();
  });

  void refreshValidation();
  void refreshDiagnostics();
})();
