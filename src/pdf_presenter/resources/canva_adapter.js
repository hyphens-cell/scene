// DOM-only integration with Canva's public viewer. No account/API credentials.
(() => {
  if (window.__sceneCanva) return;
  const labels = {
    next: /^(Next page|Next|Далее|Следующая страница)$/i,
    previous: /^(Previous page|Previous|Предыдущая страница)$/i,
  };
  const button = key => [...document.querySelectorAll('button')].find(e => labels[key].test(e.getAttribute('aria-label') || e.textContent.trim()));
  const progress = () => [...document.querySelectorAll('[role="slider"]')].find(e => /design|дизайн/i.test(e.getAttribute('aria-label') || ''));
  const videos = () => [...document.querySelectorAll('video')].filter(e => e.isConnected && e.getBoundingClientRect().width > 1 && e.getBoundingClientRect().height > 1);
  const ids = new WeakMap();
  let nextId = 1, running = false, covered = true, resume = new Set(), volume = null;
  const volumeApplied = new WeakSet();
  const loopOverrides = new WeakMap(), held = new WeakMap();
  const applyVolume = e => {
    if (volume !== null) { e.volume = volume; e.muted = false; }
    volumeApplied.add(e);
  };
  const identify = e => { if (!ids.has(e)) ids.set(e, nextId++); return ids.get(e); };
  const play = e => { const p = e.play(); if (p) p.catch(() => {}); };
  const pauseAll = () => document.querySelectorAll('video,audio').forEach(e => e.pause());
  // A late-created media element must not start during preparation, stop or a cover.
  document.addEventListener('play', event => {
    if (!volumeApplied.has(event.target)) applyVolume(event.target);
    if (!running || covered || held.has(event.target)) event.target.pause();
  }, true);
  document.addEventListener('ended', event => {
    const e = event.target;
    if (loopOverrides.get(e) === false) {
      // The viewer may implement its own on-ended restart. An explicit Repeat
      // off command takes precedence over that automatic restart.
      held.set(e, 'ended');
      e.pause();
      event.stopImmediatePropagation();
    }
  }, true);
  window.__sceneCanva = {
    state() {
      const slider = progress();
      if (!slider) return {ready: false, title: document.title};
      if (!running || covered) pauseAll();
      return {
        ready: true, title: document.title,
        count: Number(slider.getAttribute('aria-valuemax')),
        index: Number(slider.getAttribute('aria-valuenow')) - 1,
        h264: document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"'),
        videos: videos().map(e => ({id: identify(e), name: `Video ${identify(e)}`,
          state: e.readyState < 1 ? 3 : e.ended || held.get(e) === 'ended' ? 2 : e.paused ? 1 : 0,
          media_error: e.error ? e.error.message : '',
          position: Math.round(e.currentTime * 1000) || 0,
          duration: Number.isFinite(e.duration) ? Math.round(e.duration * 1000) : 0,
          volume: e.muted ? 0 : Math.round(e.volume * 100), loop: e.loop,
          seekable: Number.isFinite(e.duration) && e.duration > 0
        }))
      };
    },
    navigate(action, index) {
      if (action === 'goto') {
        window.location.hash = String(index + 1);
      } else {
        const target = button(action);
        if (!target || target.disabled) return false;
        target.click();
      }
      return true;
    },
    hideControls() {
      // Keep the real navigation controls mounted for programmatic navigation.
      // Canva's own hide command unmounts them, including the slide-count slider.
      if (!document.getElementById('scene-viewer-controls')) {
        const style = document.createElement('style');
        style.id = 'scene-viewer-controls';
        style.textContent = 'footer:has([role="slider"]),button,[role="slider"],a[href="https://www.canva.com/"]{opacity:0!important;pointer-events:none!important}';
        document.head.appendChild(style);
      }
      return true;
    },
    start(value = null) {
      volume = value === null ? null : Math.min(1, Math.max(0, value / 100));
      running = true; covered = false;
      [...videos(), ...document.querySelectorAll('audio')].forEach(e => { held.delete(e); applyVolume(e); play(e); });
    },
    stop() { running = false; covered = true; resume.clear(); pauseAll(); },
    cover(value) {
      const wasCovered = covered;
      covered = value;
      if (value && !wasCovered) {
        resume = new Set([...document.querySelectorAll('video,audio')].filter(e => !e.paused));
        pauseAll();
      } else if (!value && wasCovered && running) {
        resume.forEach(e => { if (e.isConnected) play(e); });
        resume.clear();
      }
    },
    control(id, action, value) {
      const e = videos().find(e => identify(e) === id);
      if (!running || covered || !e) return false;
      if (action === 'play') { held.delete(e); play(e); }
      else if (action === 'pause') { held.set(e, 'paused'); e.pause(); }
      else if (action === 'stop') { held.set(e, 'stopped'); e.pause(); e.currentTime = 0; }
      else if (action === 'seek' && Number.isFinite(e.duration)) {
        if (held.get(e) === 'ended') held.set(e, 'paused');
        e.currentTime = Math.min(e.duration, Math.max(0, value / 1000));
      }
      else if (action === 'volume') { volume = Math.min(1, Math.max(0, value / 100)); applyVolume(e); }
      else if (action === 'loop') { e.loop = Boolean(value); loopOverrides.set(e, e.loop); }
      else return false;
      return true;
    }
  };
})();
