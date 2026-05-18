import { Hono } from "jsr:@hono/hono";

interface Video {
  id: string;
  title: string;
  url: string;
  duration: number | null;
  channel?: string;
  alive?: boolean;
}

const raw: Video[] = JSON.parse(await Deno.readTextFile("./playlist.json"));
const PLAYLIST = raw.filter(v => v.alive !== false && typeof v.duration === "number" && v.duration > 0);
const TOTAL = PLAYLIST.reduce((s, v) => s + (v.duration as number), 0);
const EPOCH = Math.floor(Date.parse("2026-05-18T00:00:00Z") / 1000);

console.log(`tv.tools.ejfox.com — ${PLAYLIST.length} videos, ${(TOTAL/3600).toFixed(1)}h total, looping from epoch ${EPOCH}`);

function nowPlaying() {
  const t = (((Date.now() / 1000) - EPOCH) % TOTAL + TOTAL) % TOTAL;
  let acc = 0;
  for (let i = 0; i < PLAYLIST.length; i++) {
    const v = PLAYLIST[i];
    const d = v.duration as number;
    if (t < acc + d) return { video: v, offset: Math.floor(t - acc), idx: i };
    acc += d;
  }
  return { video: PLAYLIST[0], offset: 0, idx: 0 };
}

const app = new Hono();

app.get("/now", c => {
  const np = nowPlaying();
  return c.json({ ...np, total: PLAYLIST.length, runtime_seconds: TOTAL });
});

app.get("/playlist.json", c => c.json(PLAYLIST));

app.get("/", c => c.html(`<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>tv.tools.ejfox.com</title>
<style>
  :root{--pink:#e60067;--teal:#6eedf7;--muted:#735865;}
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:#000;color:#d5cdd0;font-family:ui-monospace,Menlo,monospace;overflow:hidden}
  #player{position:fixed;inset:0}
  .hud{position:fixed;bottom:18px;left:20px;right:20px;z-index:10;display:flex;align-items:end;justify-content:space-between;gap:20px;pointer-events:none;font-size:11px;letter-spacing:0.06em}
  .hud .title{color:var(--pink);font-weight:700;letter-spacing:0.14em;text-transform:uppercase;text-shadow:0 0 14px rgba(230,0,103,0.45),0 0 6px #000}
  .hud .now{color:var(--teal);text-shadow:0 0 6px #000,0 0 14px rgba(0,0,0,0.9);max-width:60vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hud .meta{color:var(--muted);text-align:right;text-transform:uppercase;letter-spacing:0.1em;text-shadow:0 0 4px #000}
  .hud .meta b{color:#d5cdd0;font-weight:400}
  #idle{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:#000;z-index:20;color:var(--muted);font-size:11px;letter-spacing:0.18em;text-transform:uppercase}
  #idle.gone{opacity:0;pointer-events:none;transition:opacity 600ms}
  #idle b{color:var(--pink);font-size:46px;display:block;margin-bottom:14px;text-shadow:0 0 24px rgba(230,0,103,0.5)}
</style>
</head><body>
<div id="idle"><div style="text-align:center"><b>tv</b>tools.ejfox.com<br><span id="boot-line">tuning in…</span></div></div>
<div id="player"></div>
<div class="hud">
  <div>
    <div class="title">tv.tools.ejfox.com</div>
    <div class="now" id="now">—</div>
  </div>
  <div class="meta">
    <span id="idx">…</span> · <b id="runtime">…</b>
  </div>
</div>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
let player, current = null;

async function fetchNow() {
  const r = await fetch('/now');
  return await r.json();
}
function renderHud(d) {
  document.getElementById('now').textContent = (d.video.title || d.video.id) + (d.video.channel ? ' · ' + d.video.channel : '');
  document.getElementById('idx').textContent = (d.idx + 1) + ' / ' + d.total;
  const h = Math.floor(d.runtime_seconds / 3600);
  document.getElementById('runtime').textContent = h + 'h loop';
}
async function syncToNow(loadInitial = false) {
  const d = await fetchNow();
  renderHud(d);
  if (loadInitial) {
    current = d.video;
    return d;
  }
  if (!current || current.id !== d.video.id) {
    current = d.video;
    if (player && player.loadVideoById) {
      player.loadVideoById({ videoId: d.video.id, startSeconds: d.offset });
    }
  }
  return d;
}
window.onYouTubeIframeAPIReady = async () => {
  const d = await syncToNow(true);
  player = new YT.Player('player', {
    height: '100%', width: '100%',
    videoId: d.video.id,
    playerVars: { autoplay: 1, mute: 1, controls: 1, modestbranding: 1, rel: 0, start: d.offset, playsinline: 1 },
    events: {
      onReady: e => {
        e.target.playVideo();
        document.getElementById('boot-line').textContent = 'live';
        setTimeout(() => document.getElementById('idle').classList.add('gone'), 400);
      },
      onStateChange: e => { if (e.data === YT.PlayerState.ENDED) syncToNow(); },
      onError: () => syncToNow()   // skip dead/unembeddable
    }
  });
  setInterval(syncToNow, 60000);   // re-sync every minute against server clock
};
</script>
</body></html>`));

export default { fetch: app.fetch };
