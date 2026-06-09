/**
 * Portal — Berserk · Single Viewport
 *
 * Entrance GSAP timeline, expandable sidebar, BGM player with custom UI.
 */

document.addEventListener('DOMContentLoaded', () => {
  initEntrance();
  initSidebar();
  initBgmPlayer();
});

/* ══════════════════════════════════════════════════════════════
   Entrance — staggered GSAP timeline
   ══════════════════════════════════════════════════════════════ */
function initEntrance() {
  const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });

  // Brand rises from the dark
  tl.fromTo(
    '.brand',
    { opacity: 0, y: -14, filter: 'blur(6px)' },
    { opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.9 },
    0.2
  );

  // BGM player slides in from right
  tl.fromTo(
    '.bgm-player',
    { opacity: 0, x: 16 },
    { opacity: 1, x: 0, duration: 0.6 },
    '-=0.3'
  );

  // Sidebar trigger
  tl.fromTo(
    '.sidebar-trigger',
    { opacity: 0 },
    { opacity: 1, duration: 0.5 },
    '-=0.2'
  );
}

/* ══════════════════════════════════════════════════════════════
   Sidebar — hover-triggered expansion
   ══════════════════════════════════════════════════════════════ */
function initSidebar() {
  const sidebar = document.getElementById('sidebar');
  const trigger = document.getElementById('sidebarTrigger');
  const panel = document.getElementById('sidebarPanel');
  if (!sidebar || !trigger) return;

  let hoverTimeout = null;
  let locked = false;

  // Hover on trigger: expand
  trigger.addEventListener('mouseenter', () => {
    clearTimeout(hoverTimeout);
    sidebar.classList.add('expanded');
  });

  // Hover on entire sidebar area (keeps it open)
  sidebar.addEventListener('mouseenter', () => {
    clearTimeout(hoverTimeout);
    sidebar.classList.add('expanded');
  });

  // Mouse leaves sidebar: collapse after delay
  sidebar.addEventListener('mouseleave', () => {
    hoverTimeout = setTimeout(() => {
      if (!locked) {
        sidebar.classList.remove('expanded');
      }
    }, 400);
  });

  // Click trigger: toggle lock (for mobile / intentional open)
  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    locked = !locked;
    if (locked) {
      sidebar.classList.add('expanded');
    } else {
      sidebar.classList.remove('expanded');
    }
  });

  // Click outside sidebar: unlock & collapse
  document.addEventListener('click', (e) => {
    if (locked && !sidebar.contains(e.target)) {
      locked = false;
      sidebar.classList.remove('expanded');
    }
  });

  // Keyboard: Escape to close
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && locked) {
      locked = false;
      sidebar.classList.remove('expanded');
    }
  });
}

/* ══════════════════════════════════════════════════════════════
   BGM Player — audio loading, play/pause, volume
   ══════════════════════════════════════════════════════════════ */
function initBgmPlayer() {
  const audio = document.getElementById('bgmAudio');
  const toggleBtn = document.getElementById('bgmToggle');
  const volumeSlider = document.getElementById('bgmVolume');
  const trackLabel = document.getElementById('bgmTrack');

  if (!audio || !toggleBtn || !volumeSlider) return;

  // ── BGM Playlist ────────────────────────────────────────
  const playlist = [
    { file: '/bgm/Frank Ocean - Self Control.mp3',    name: 'Self Control' },
    { file: '/bgm/Frank Ocean - Pink + White.mp3',    name: 'Pink + White' },
    { file: '/bgm/Frank Ocean - Solo.mp3',            name: 'Solo' },
    { file: '/bgm/Frank Ocean - White Ferrari.mp3',   name: 'White Ferrari' },
  ];

  let loaded = false;
  let currentIdx = 0;

  function extractName(src) {
    const match = playlist.find(p => src.endsWith(p.file) || src.includes(p.file));
    return match ? match.name : '';
  }

  function loadTrack(idx) {
    if (idx >= playlist.length) return;
    currentIdx = idx;
    audio.src = playlist[idx].file;
    audio.load();
  }

  function showTrack(name) {
    if (!trackLabel) return;
    if (name) {
      trackLabel.textContent = name;
      trackLabel.classList.add('show');
    } else {
      trackLabel.classList.remove('show');
    }
  }

  audio.addEventListener('canplaythrough', () => {
    if (!loaded) {
      loaded = true;
      audio.volume = parseFloat(volumeSlider.value) / 100;
      const name = extractName(audio.src);
      showTrack(name);
      console.log(`[BGM] Loaded: ${name}`);
    }
  }, { once: false });

  audio.addEventListener('error', () => {
    if (!loaded) {
      // Try next track in playlist
      loadTrack(currentIdx + 1);
    }
  });

  // When track ends, play next
  audio.addEventListener('ended', () => {
    const next = (currentIdx + 1) % playlist.length;
    loadTrack(next);
    const name = extractName(playlist[next].file);
    showTrack(name);
    audio.play().then(() => {
      toggleBtn.classList.add('playing');
    }).catch(() => {});
  });

  // Kick off
  loadTrack(0);

  // ── Play / Pause ────────────────────────────────────────
  toggleBtn.addEventListener('click', () => {
    if (!loaded) {
      loadTrack(0);
      return;
    }
    if (audio.paused) {
      audio.play().then(() => {
        toggleBtn.classList.add('playing');
        const name = extractName(audio.src);
        showTrack(name);
      }).catch((err) => {
        console.warn('[BGM] Playback blocked:', err.message);
      });
    } else {
      audio.pause();
      toggleBtn.classList.remove('playing');
    }
  });

  // ── Volume ──────────────────────────────────────────────
  volumeSlider.addEventListener('input', () => {
    audio.volume = parseFloat(volumeSlider.value) / 100;
  });

  // ── Keyboard shortcut: Space to toggle (only when not typing) ──
  document.addEventListener('keydown', (e) => {
    if (
      e.code === 'Space' &&
      !e.target.closest('input, textarea, [contenteditable]') &&
      !e.repeat
    ) {
      e.preventDefault();
      toggleBtn.click();
    }
  });
}
