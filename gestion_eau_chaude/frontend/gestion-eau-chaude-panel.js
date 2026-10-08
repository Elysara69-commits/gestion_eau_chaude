/* Panneau « Eau chaude » : visuel dynamique du chauffe-eau électrique.
 * Composant web autonome, alimenté par la commande WebSocket gestion_eau_chaude/subscribe. */

const STATUS = {
  unavailable:   { label: "Interrupteur indisponible",          color: "#9e9e9e", heat: 0 },
  heating_solar: { label: "Chauffe solaire en cours",           color: "#ffb300", heat: 1 },
  heating_night: { label: "Chauffe en heures creuses",          color: "#7c9cff", heat: 1 },
  heating_manual:{ label: "Marche forcée",                      color: "#ff7043", heat: 1 },
  thermostat:    { label: "Ballon chaud : thermostat atteint",  color: "#ffa726", heat: 0.75 },
  locked:        { label: "Redémarrage verrouillé",             color: "#ef5350", heat: 0.12 },
  done:          { label: "Cycle terminé, ballon chaud",        color: "#66bb6a", heat: 0.75 },
  waiting_solar: { label: "En attente de surplus solaire",      color: "#26c6da", heat: 0.12 },
  standby:       { label: "Veille",                             color: "#90a4ae", heat: 0.12 },
};

const MODE_LABEL = { solar: "☀️ Solaire", night: "🌙 Heures creuses", manual: "🔧 Forcé / manuel" };

const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const W = (v) => (v == null ? "—" : nf.format(Math.round(v)));
const hh = (h) => String(h).padStart(2, "0") + "h";
const mmss = (s) => {
  s = Math.max(0, Math.floor(s));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

const METRICS = [
  { id: "solar",   icon: "mdi:white-balance-sunny", title: "Production solaire",  unit: "W" },
  { id: "soc",     icon: "mdi:battery-high",        title: "Batterie",            unit: "%" },
  { id: "grid",    icon: "mdi:transmission-tower",  title: "Import réseau",       unit: "W" },
  { id: "house",   icon: "mdi:home-lightning-bolt", title: "Consommation maison", unit: "W" },
  { id: "surplus", icon: "mdi:solar-power-variant", title: "Surplus solaire",     unit: "W" },
  { id: "heater",  icon: "mdi:water-boiler",        title: "Chauffe-eau",         unit: "W" },
];

const metricCard = (m) => `
  <div class="card metric" id="card-${m.id}">
    <div class="mh"><ha-icon icon="${m.icon}"></ha-icon><span>${m.title}</span></div>
    <div class="mv"><b id="${m.id}-v">—</b><small>${m.unit}</small></div>
    <div class="bar"><i id="${m.id}-b"></i><u id="${m.id}-m1"></u><u id="${m.id}-m2"></u></div>
    <div class="sub" id="${m.id}-s"></div>
  </div>`;

const TEMPLATE = `
<style>
  :host {
    display: block; min-height: 100vh; box-sizing: border-box;
    background: var(--primary-background-color, #111);
    color: var(--primary-text-color, #eee);
    --card: var(--card-background-color, #1c1c1c);
    --line: var(--divider-color, rgba(255,255,255,.12));
    --muted: var(--secondary-text-color, #9e9e9e);
    --accent: #90a4ae;
    --ok: #66bb6a; --warn: #ffa726; --bad: #ef5350;
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  * { box-sizing: border-box; }
  header {
    display: flex; align-items: center; gap: 12px; padding: 8px 16px; min-height: 56px;
    background: var(--app-header-background-color, var(--card)); border-bottom: 1px solid var(--line);
    position: sticky; top: 0; z-index: 5;
  }
  header h1 { font-size: 20px; font-weight: 500; margin: 0; flex: 1; }
  .pill {
    display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 999px;
    font-size: 14px; font-weight: 500; color: #fff; background: var(--accent); transition: background .6s;
  }
  .pill i { width: 9px; height: 9px; border-radius: 50%; background: #fff; display: inline-block; }
  .pill.live i { animation: blink 1.4s infinite; }
  #clock { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 14px; }
  main { padding: 16px; max-width: 1400px; margin: 0 auto; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 14px 16px; }
  .card h2 { margin: 0 0 10px; font-size: 15px; font-weight: 500; display: flex; align-items: center; gap: 8px; }
  .card h2 ha-icon { --mdc-icon-size: 20px; color: var(--muted); }
  .hero { display: grid; grid-template-columns: 1fr minmax(260px, 340px) 1fr; gap: 16px; align-items: start; }
  .col { display: flex; flex-direction: column; gap: 12px; }
  .center { display: flex; flex-direction: column; align-items: center; gap: 12px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-top: 16px; }
  @media (max-width: 1000px) { .hero { grid-template-columns: 1fr 1fr; } .center { grid-column: 1 / -1; order: -1; } }
  @media (max-width: 620px)  { .hero { grid-template-columns: 1fr; } main { padding: 10px; } }

  /* Cartes de mesure */
  .mh { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }
  .mh ha-icon { --mdc-icon-size: 20px; }
  .mv { margin: 4px 0 8px; font-variant-numeric: tabular-nums; }
  .mv b { font-size: 30px; font-weight: 500; }
  .mv small { font-size: 14px; color: var(--muted); margin-left: 4px; }
  .bar { position: relative; height: 8px; background: var(--line); border-radius: 4px; }
  .bar i { position: absolute; inset: 0 auto 0 0; width: 0; border-radius: 4px; background: var(--ok); transition: width .8s, background .4s; }
  .bar i.warn { background: var(--warn); } .bar i.bad { background: var(--bad); } .bar i.cold { background: #42a5f5; }
  .bar u { position: absolute; top: -3px; width: 2px; height: 14px; background: var(--primary-text-color, #fff); opacity: .65; display: none; }
  .sub { margin-top: 8px; font-size: 12px; color: var(--muted); min-height: 15px; }

  /* Chauffe-eau */
  #heater { width: 100%; max-width: 250px; height: auto; filter: drop-shadow(0 8px 18px rgba(0,0,0,.35)); }
  #hot { transition: opacity 1.6s; }
  #elem { transition: stroke .6s; }
  #heater.heating #elem { animation: glow 1.6s ease-in-out infinite; }
  #heater .bubble { opacity: 0; }
  #heater.heating .bubble { animation: rise 3.2s ease-in infinite; }
  #heater .wave { animation: wave 5s linear infinite; }
  .power { text-align: center; }
  .power b { font-size: 34px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .power small { color: var(--muted); font-size: 14px; margin-left: 4px; }
  .power div { color: var(--muted); font-size: 13px; margin-top: 2px; }
  .force { width: 100%; display: flex; align-items: center; gap: 12px; }
  .force .txt { flex: 1; } .force b { font-size: 15px; font-weight: 500; }
  .force small { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; line-height: 1.35; }
  .sw { position: relative; width: 58px; height: 32px; flex: none; }
  .sw input { opacity: 0; width: 0; height: 0; }
  .sw span { position: absolute; inset: 0; border-radius: 16px; background: var(--line); cursor: pointer; transition: background .3s; }
  .sw span::after { content: ""; position: absolute; width: 26px; height: 26px; left: 3px; top: 3px; border-radius: 50%; background: #fff; transition: transform .3s; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
  .sw input:checked + span { background: #ff7043; }
  .sw input:checked + span::after { transform: translateX(26px); }
  .sw input:disabled + span { opacity: .5; cursor: wait; }
  .btn { width: 100%; padding: 10px; border-radius: 12px; border: 1px solid var(--bad); background: transparent; color: var(--bad); font-size: 14px; cursor: pointer; display: none; }
  .btn:hover { background: rgba(239,83,80,.12); }

  /* Détails */
  .rows { display: flex; flex-direction: column; gap: 10px; }
  .row { display: flex; align-items: flex-start; gap: 10px; font-size: 14px; }
  .row .ic { width: 28px; height: 28px; border-radius: 50%; flex: none; display: flex; align-items: center; justify-content: center; background: var(--line); font-size: 15px; }
  .row.ok .ic { background: rgba(102,187,106,.22); } .row.warn .ic { background: rgba(255,167,38,.22); } .row.bad .ic { background: rgba(239,83,80,.22); }
  .row .t small { display: block; color: var(--muted); font-size: 12px; margin-top: 1px; }
  .energy { display: flex; align-items: baseline; gap: 6px; }
  .energy b { font-size: 36px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .energy small { color: var(--muted); font-size: 15px; }
  .stack { display: flex; height: 14px; border-radius: 7px; overflow: hidden; background: var(--line); margin: 10px 0; }
  .stack i { display: block; height: 100%; transition: width .8s; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); }
  .legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; background: var(--c); }
  .legend b { color: var(--primary-text-color, #eee); font-weight: 500; font-variant-numeric: tabular-nums; }

  .timeline { position: relative; height: 34px; background: var(--line); border-radius: 8px; margin: 22px 0 22px; }
  .timeline .seg { position: absolute; top: 0; bottom: 0; border-radius: 8px; opacity: .85; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #111; font-weight: 600; overflow: hidden; }
  .timeline .now { position: absolute; top: -8px; bottom: -8px; width: 3px; background: #fff; border-radius: 2px; box-shadow: 0 0 8px #fff; z-index: 2; }
  .timeline .tick { position: absolute; top: 38px; transform: translateX(-50%); font-size: 11px; color: var(--muted); }

  ul.check { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 7px; font-size: 14px; }
  ul.check li { display: flex; align-items: center; gap: 10px; }
  ul.check li::before { content: "✗"; width: 22px; height: 22px; border-radius: 50%; background: rgba(239,83,80,.2); color: var(--bad); display: inline-flex; align-items: center; justify-content: center; font-size: 13px; flex: none; }
  ul.check li.ok::before { content: "✓"; background: rgba(102,187,106,.22); color: var(--ok); }
  ul.check li.na { opacity: .5; }
  ul.check li.na::before { content: "–"; background: var(--line); color: var(--muted); }
  .timer { margin-top: 12px; font-size: 13px; color: var(--muted); }
  .timer .bar { margin-top: 6px; }
  .safety { display: flex; flex-direction: column; gap: 12px; }
  .safety .top { display: flex; justify-content: space-between; font-size: 14px; gap: 8px; }
  .safety .top span:last-child { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 13px; white-space: nowrap; }
  .safety .bar { margin-top: 6px; height: 6px; }
  .log { max-height: 280px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
  .log div { display: flex; gap: 10px; line-height: 1.35; }
  .log time { color: var(--muted); font-variant-numeric: tabular-nums; flex: none; }
  .log .start { color: #ffb74d; } .log .warn { color: var(--warn); } .log .error { color: var(--bad); }
  .empty { color: var(--muted); font-size: 13px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chips span { background: var(--line); border-radius: 999px; padding: 5px 12px; font-size: 12px; }
  .chips b { font-weight: 500; }
  .hint { color: var(--muted); font-size: 12px; margin-top: 10px; }
  .err { padding: 24px; text-align: center; color: var(--bad); }

  @keyframes blink { 50% { opacity: .25; } }
  @keyframes glow { 50% { opacity: .55; } }
  @keyframes rise { 0% { transform: translateY(0); opacity: 0; } 15% { opacity: .75; } 100% { transform: translateY(-190px); opacity: 0; } }
  @keyframes wave { from { transform: translateX(0); } to { transform: translateX(-60px); } }
</style>

<header>
  <ha-menu-button id="menu"></ha-menu-button>
  <h1>Gestion eau chaude</h1>
  <span id="pill" class="pill"><i></i><span id="pill-t">Connexion…</span></span>
  <span id="clock"></span>
</header>

<main>
  <div class="err" id="err" style="display:none"></div>

  <section class="hero">
    <div class="col">${METRICS.slice(0, 3).map(metricCard).join("")}</div>

    <div class="center">
      <svg id="heater" viewBox="0 0 220 440" role="img" aria-label="Chauffe-eau électrique">
        <defs>
          <linearGradient id="shell" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stop-color="#b0bec5"/><stop offset=".22" stop-color="#ffffff"/>
            <stop offset=".62" stop-color="#eceff1"/><stop offset="1" stop-color="#90a4ae"/>
          </linearGradient>
          <linearGradient id="cold" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stop-color="#4fc3f7"/><stop offset="1" stop-color="#01579b"/>
          </linearGradient>
          <linearGradient id="warm" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stop-color="#ffe082"/><stop offset=".5" stop-color="#ff9800"/><stop offset="1" stop-color="#d84315"/>
          </linearGradient>
          <clipPath id="tankClip"><rect x="52" y="84" width="116" height="250" rx="16"/></clipPath>
        </defs>

        <!-- raccords eau froide / eau chaude -->
        <rect x="62" y="12" width="16" height="32" rx="3" fill="#78909c"/>
        <rect x="62" y="12" width="16" height="7" rx="2" fill="#42a5f5"/>
        <rect x="142" y="12" width="16" height="32" rx="3" fill="#78909c"/>
        <rect x="142" y="12" width="16" height="7" rx="2" fill="#ef5350"/>
        <!-- pieds -->
        <rect x="50" y="402" width="16" height="22" rx="3" fill="#546e7a"/>
        <rect x="154" y="402" width="16" height="22" rx="3" fill="#546e7a"/>
        <!-- cuve -->
        <path d="M30 82 C30 54 62 38 110 38 C158 38 190 54 190 82 L190 392 C190 406 158 412 110 412 C62 412 30 406 30 392 Z"
              fill="url(#shell)" stroke="#b0bec5" stroke-width="2"/>
        <path d="M44 84 C44 64 70 52 110 52" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".7"/>

        <!-- fenêtre de visualisation -->
        <rect x="48" y="80" width="124" height="258" rx="20" fill="#0d2230"/>
        <g clip-path="url(#tankClip)">
          <rect x="52" y="84" width="116" height="250" fill="url(#cold)"/>
          <rect id="hot" x="52" y="84" width="116" height="250" fill="url(#warm)" opacity="0.12"/>
          <g class="wave"><path d="M-8 104 q15 -9 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 V84 H-8 Z" fill="#0d2230" opacity=".55"/></g>
          <!-- résistance chauffante -->
          <path id="elem" d="M66 296 H154 C166 296 166 312 154 312 H66 C54 312 54 328 66 328 H154"
                fill="none" stroke="#78909c" stroke-width="5" stroke-linecap="round"/>
          <!-- bulles -->
          <circle class="bubble" cx="76"  cy="300" r="4"   fill="#fff" style="animation-delay:0s"/>
          <circle class="bubble" cx="100" cy="310" r="3"   fill="#fff" style="animation-delay:.9s"/>
          <circle class="bubble" cx="122" cy="302" r="5"   fill="#fff" style="animation-delay:1.7s"/>
          <circle class="bubble" cx="144" cy="312" r="3.5" fill="#fff" style="animation-delay:2.3s"/>
          <circle class="bubble" cx="110" cy="318" r="2.5" fill="#fff" style="animation-delay:1.3s"/>
        </g>
        <rect x="48" y="80" width="124" height="258" rx="20" fill="none" stroke="#cfd8dc" stroke-width="3"/>

        <!-- boîtier de commande + thermostat -->
        <rect x="42" y="348" width="62" height="46" rx="8" fill="#fafafa" stroke="#b0bec5" stroke-width="1.5"/>
        <circle id="led" cx="52" cy="358" r="3.5" fill="#90a4ae"/>
        <rect x="58" y="354" width="38" height="8" rx="2" fill="#cfd8dc"/>
        <text id="boxW" x="73" y="380" text-anchor="middle" font-size="10" font-weight="600" fill="#37474f">— W</text>
        <circle cx="146" cy="372" r="13" fill="#cfd8dc" stroke="#90a4ae" stroke-width="1.5"/>
        <circle cx="146" cy="372" r="8" fill="#eceff1" stroke="#b0bec5"/>
        <rect x="144.5" y="364" width="3" height="8" rx="1.5" fill="#78909c"/>
      </svg>

      <div class="power">
        <div><b id="heater-big">—</b><small>W</small></div>
        <div id="source">—</div>
      </div>

      <div class="card force">
        <div class="txt">
          <b>Marche forcée</b>
          <small>Allume le chauffe-eau sans condition solaire ni horaire. Les sécurités (surconsommation, fin de cycle) restent actives.</small>
        </div>
        <label class="sw"><input type="checkbox" id="force"><span></span></label>
      </div>
      <button class="btn" id="stop">Couper le chauffe-eau maintenant</button>
    </div>

    <div class="col">${METRICS.slice(3).map(metricCard).join("")}</div>
  </section>

  <section class="cards">
    <div class="card">
      <h2><ha-icon icon="mdi:lightning-bolt"></ha-icon>Consommation du jour</h2>
      <div class="energy"><b id="kwh-total">0,00</b><small>kWh</small></div>
      <div class="stack"><i id="seg-solar" style="background:#ffb300;width:0"></i><i id="seg-night" style="background:#7c9cff;width:0"></i><i id="seg-manual" style="background:#ff7043;width:0"></i></div>
      <div class="legend">
        <span style="--c:#ffb300">Solaire <b id="kwh-solar">0,00</b> kWh</span>
        <span style="--c:#7c9cff">Heures creuses <b id="kwh-night">0,00</b> kWh</span>
        <span style="--c:#ff7043">Forcé <b id="kwh-manual">0,00</b> kWh</span>
      </div>
    </div>

    <div class="card">
      <h2><ha-icon icon="mdi:calendar-today"></ha-icon>Aujourd'hui</h2>
      <div class="rows">
        <div class="row" id="r-solar"><div class="ic">☀️</div><div class="t"><span id="r-solar-t"></span><small id="r-solar-s"></small></div></div>
        <div class="row" id="r-night"><div class="ic">🌙</div><div class="t"><span id="r-night-t"></span><small id="r-night-s"></small></div></div>
        <div class="row" id="r-cycle"><div class="ic">✅</div><div class="t"><span id="r-cycle-t"></span><small id="r-cycle-s"></small></div></div>
        <div class="row" id="r-lock"><div class="ic">🔒</div><div class="t"><span id="r-lock-t"></span><small id="r-lock-s"></small></div></div>
      </div>
    </div>

    <div class="card">
      <h2><ha-icon icon="mdi:clock-outline"></ha-icon>Plages horaires</h2>
      <div class="timeline" id="timeline"></div>
      <div class="hint" id="tl-hint"></div>
    </div>

    <div class="card">
      <h2><ha-icon icon="mdi:flash-auto"></ha-icon>Démarrage solaire</h2>
      <ul class="check">
        <li id="c-in_solar"></li><li id="c-not_done"></li><li id="c-can_start"></li>
        <li id="c-solar"></li><li id="c-soc"></li><li id="c-surplus"></li>
      </ul>
      <div class="timer" id="t-solar"></div>
    </div>

    <div class="card">
      <h2><ha-icon icon="mdi:shield-check-outline"></ha-icon>Sécurités</h2>
      <div class="safety" id="safety">
        <div><div class="top"><span>Surconsommation + import réseau</span><span id="s-overload-t"></span></div><div class="bar"><i id="s-overload-b"></i></div></div>
        <div><div class="top"><span>Batterie sous le seuil d'arrêt</span><span id="s-battery_low-t"></span></div><div class="bar"><i id="s-battery_low-b"></i></div></div>
        <div><div class="top"><span>Fin de cycle (ballon à ~0 W)</span><span id="s-idle-t"></span></div><div class="bar"><i id="s-idle-b"></i></div></div>
        <div><div class="top"><span>Mesures indisponibles (mode solaire)</span><span id="s-data_lost-t"></span></div><div class="bar"><i id="s-data_lost-b"></i></div></div>
      </div>
    </div>

    <div class="card">
      <h2><ha-icon icon="mdi:history"></ha-icon>Journal</h2>
      <div class="log" id="log"></div>
    </div>

    <div class="card">
      <h2><ha-icon icon="mdi:tune"></ha-icon>Réglages actifs</h2>
      <div class="chips" id="chips"></div>
      <div class="hint">Modifiables dans Paramètres → Appareils et services → Gestion eau chaude → Configurer.</div>
    </div>
  </section>
</main>
`;

class GestionEauChaudePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._snap = null;
    this._recv = 0;
    this._unsub = null;
    this._subscribing = false;
    this._pending = false;
    this._built = false;
    this._el = {};
    this._sig = {};
  }

  /* --- cycle de vie ------------------------------------------------------ */
  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    if (this._menu) this._menu.hass = hass;
    this._subscribe();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) this._menu.narrow = narrow;
  }

  set panel(panel) { this._panel = panel; }

  connectedCallback() {
    this._timer = setInterval(() => this._render(), 1000);
    this._subscribe();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._unsub) { this._unsub(); this._unsub = null; }
  }

  _build() {
    this.shadowRoot.innerHTML = TEMPLATE;
    this.shadowRoot.querySelectorAll("[id]").forEach((e) => { this._el[e.id] = e; });
    this._menu = this._el.menu;
    if (this._hass) this._menu.hass = this._hass;
    if (this._narrow !== undefined) this._menu.narrow = this._narrow;

    this._el.force.addEventListener("change", (e) => this._send(e.target.checked, e.target));
    this._el.stop.addEventListener("click", () => this._send(false, this._el.stop));
    this._built = true;
  }

  async _subscribe() {
    if (!this._hass || !this.isConnected || this._unsub || this._subscribing) return;
    this._subscribing = true;
    try {
      const unsub = await this._hass.connection.subscribeMessage(
        (snap) => { this._snap = snap; this._recv = Date.now(); this._render(); },
        { type: "gestion_eau_chaude/subscribe" }
      );
      if (this.isConnected) this._unsub = unsub; else unsub();
      this._showError(null);
    } catch (err) {
      this._showError(
        "Impossible de joindre l'intégration : " + (err && err.message ? err.message : JSON.stringify(err))
      );
    } finally {
      this._subscribing = false;
    }
  }

  async _send(on, control) {
    this._pending = true;
    control.disabled = true;
    try {
      await this._hass.connection.sendMessagePromise({ type: "gestion_eau_chaude/force", on });
    } catch (err) {
      this._toast("Commande refusée : " + (err && err.message ? err.message : "erreur"));
    } finally {
      this._pending = false;
      control.disabled = false;
      this._render();
    }
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  _showError(msg) {
    if (!this._el.err) return;
    this._el.err.style.display = msg ? "block" : "none";
    this._el.err.textContent = msg || "";
  }

  /* --- helpers d'affichage ------------------------------------------------- */
  _txt(id, text) {
    const el = this._el[id];
    if (el && el.textContent !== text) el.textContent = text;
  }

  _row(id, cls, title, sub) {
    const el = this._el[id];
    if (!el) return;
    el.className = "row " + cls;
    this._txt(id + "-t", title);
    this._txt(id + "-s", sub || "");
  }

  _html(id, html) {
    const el = this._el[id];
    if (el && el.innerHTML !== html) el.innerHTML = html;
  }

  _metric(id, value, max, markers, sub, cls) {
    const pct = (v) => Math.max(0, Math.min(100, (v / max) * 100));
    this._txt(id + "-v", value == null ? "—" : W(value));
    const bar = this._el[id + "-b"];
    bar.style.width = value == null ? "0%" : pct(value) + "%";
    bar.className = cls || "";
    [1, 2].forEach((n) => {
      const el = this._el[`${id}-m${n}`];
      const m = markers[n - 1];
      if (m == null) { el.style.display = "none"; return; }
      el.style.left = `calc(${pct(m)}% - 1px)`;
      el.style.display = "block";
    });
    this._txt(id + "-s", sub);
  }

  _timerBar(key, label, enabledText, snap, extra) {
    const t = snap.timers[key];
    const dt = (Date.now() - this._recv) / 1000;
    const elapsed = t.active ? Math.min(t.hold, t.elapsed + dt) : 0;
    const bar = this._el[`s-${key}-b`];
    bar.style.width = (t.hold ? (elapsed / t.hold) * 100 : 0) + "%";
    bar.className = t.active ? (elapsed >= t.hold ? "bad" : "warn") : "";
    this._txt(`s-${key}-t`, t.active ? `${mmss(elapsed)} / ${mmss(t.hold)}` : enabledText);
  }

  /* --- rendu ---------------------------------------------------------------- */
  _render() {
    if (!this._built) return;
    const snap = this._snap;
    if (!snap || !snap.status) {
      this._txt("pill-t", this._el.err.style.display === "block" ? "Erreur" : "Chargement…");
      return;
    }
    const dt = (Date.now() - this._recv) / 1000;
    const st = STATUS[snap.status] || STATUS.standby;
    const v = snap.values, set = snap.settings, sch = snap.schedule;
    const heating = snap.status.startsWith("heating");

    // En-tête
    this.style.setProperty("--accent", st.color);
    this._txt("pill-t", st.label);
    this._el.pill.className = "pill" + (heating ? " live" : "");
    const hourNow = (snap.hour + dt / 3600) % 24;
    this._txt("clock", `${String(Math.floor(hourNow)).padStart(2, "0")}:${String(Math.floor((hourNow % 1) * 60)).padStart(2, "0")}`);

    // Chauffe-eau (SVG)
    this._el.heater.classList.toggle("heating", heating);
    this._el.hot.style.opacity = st.heat;
    this._el.elem.setAttribute("stroke", heating ? "#ff5722" : (snap.status === "thermostat" || snap.status === "done") ? "#ffa726" : "#78909c");
    this._el.led.setAttribute("fill", st.color);
    this._txt("boxW", v.heater_w == null ? "— W" : `${W(v.heater_w)} W`);
    this._txt("heater-big", W(v.heater_w));
    this._txt("source", snap.switch === "on" ? "Source : " + (MODE_LABEL[snap.mode] || MODE_LABEL.manual) : snap.switch === "off" ? "Chauffe-eau à l'arrêt" : "État inconnu");

    // Marche forcée
    if (!this._pending) this._el.force.checked = !!snap.forced;
    this._el.force.disabled = this._pending || snap.switch == null;
    this._el.stop.style.display = snap.switch === "on" && !snap.forced ? "block" : "none";

    // Mesures
    const solarMax = Math.max(3500, set.start_solar_w * 1.6);
    this._metric("solar", v.solar_w, solarMax, [set.start_solar_w], `Seuil de démarrage : ${W(set.start_solar_w)} W`,
      v.solar_w != null && v.solar_w > set.start_solar_w ? "" : "warn");
    this._metric("soc", v.soc, 100, [set.stop_soc, set.start_soc], `Arrêt < ${W(set.stop_soc)} % · démarrage ≥ ${W(set.start_soc)} %`,
      v.soc == null ? "" : v.soc >= set.start_soc ? "" : v.soc >= set.stop_soc ? "warn" : "bad");
    this._metric("grid", v.grid_w, Math.max(600, set.max_grid_import_w * 3), [set.max_grid_import_w], `Seuil anormal : ${W(set.max_grid_import_w)} W`,
      v.grid_w != null && v.grid_w > set.max_grid_import_w ? "bad" : "");
    this._metric("house", v.house_w, Math.max(4500, set.max_house_power_w * 1.3), [set.max_house_power_w], `Seuil trop fort : ${W(set.max_house_power_w)} W`,
      v.house_w != null && v.house_w > set.max_house_power_w ? "bad" : "");
    this._metric("surplus", v.surplus_w, Math.max(3000, set.min_surplus_w * 2), [set.min_surplus_w], `Requis au démarrage : ${W(set.min_surplus_w)} W (production − maison)`,
      v.surplus_w != null && v.surplus_w >= set.min_surplus_w ? "" : "warn");
    this._metric("heater", v.heater_w, 2500, [set.heater_off_w], `Considéré arrêté sous ${W(set.heater_off_w)} W`,
      heating ? "warn" : "cold");

    // Énergie du jour
    const e = snap.energy;
    this._txt("kwh-total", nf2.format(e.total));
    this._txt("kwh-solar", nf2.format(e.solar));
    this._txt("kwh-night", nf2.format(e.night));
    this._txt("kwh-manual", nf2.format(e.manual));
    const tot = e.total || 1;
    this._el["seg-solar"].style.width = (e.solar / tot) * 100 + "%";
    this._el["seg-night"].style.width = (e.night / tot) * 100 + "%";
    this._el["seg-manual"].style.width = (e.manual / tot) * 100 + "%";

    // Aujourd'hui
    this._row("r-solar", snap.ran_solar ? "ok" : "",
      snap.ran_solar ? "A chauffé sur le solaire aujourd'hui" : "Pas encore chauffé sur le solaire",
      snap.ran_solar ? `${nf2.format(e.solar)} kWh d'origine solaire` : `Plage solaire ${hh(sch.solar_start_h)}–${hh(sch.solar_end_h)}`);

    const plan = {
      running:    ["warn", "Chauffe en heures creuses en cours", `Jusqu'à ${hh(sch.hc_end_h)}`],
      planned:    ["warn", "Heures creuses : chauffe prévue cette nuit", `${hh(sch.hc_start_h)}–${hh(sch.hc_end_h)} si le cycle n'est pas terminé d'ici là`],
      not_needed: ["ok",   "Heures creuses : inutile cette nuit", "Cycle de chauffe déjà terminé"],
      off_season: ["",     "Heures creuses : hors saison", "Actives de novembre à mars uniquement"],
    }[snap.night_plan];
    this._row("r-night", plan[0], snap.ran_night ? "A chauffé en heures creuses (" + nf2.format(e.night) + " kWh)" : plan[1],
      snap.ran_night ? plan[1] : plan[2]);

    this._row("r-cycle", snap.cycle_done ? "ok" : "",
      snap.cycle_done ? "Cycle de chauffe terminé" : "Cycle de chauffe pas encore terminé",
      `Journée de chauffe : ${hh(sch.hc_end_h)} → ${hh(sch.hc_end_h)}`);

    const lockLeft = Math.max(0, snap.lock.remaining_s - dt);
    this._row("r-lock", lockLeft > 0 ? "bad" : "",
      lockLeft > 0 ? `Redémarrage verrouillé (${mmss(lockLeft)})` : "Redémarrage automatique libre",
      lockLeft > 0 && snap.lock.reason ? `Cause : ${snap.lock.reason}` : "");

    // Plages horaires (24 h)
    const sig = JSON.stringify([sch.solar_start_h, sch.solar_end_h, sch.hc_start_h, sch.hc_end_h, sch.winter]);
    if (this._sig.tl !== sig) {
      this._sig.tl = sig;
      const seg = (a, b, color, text, off) =>
        `<div class="seg" style="left:${(a / 24) * 100}%;width:${((b - a) / 24) * 100}%;background:${color};${off ? "opacity:.3" : ""}">${text}</div>`;
      const ticks = [0, 6, 12, 18, 24].map((h) => `<div class="tick" style="left:${(h / 24) * 100}%">${hh(h % 24)}</div>`).join("");
      this._html("timeline",
        seg(sch.hc_start_h, sch.hc_end_h, "#7c9cff", "🌙", !sch.winter) +
        seg(sch.solar_start_h, sch.solar_end_h, "#ffb300", "☀️ solaire", false) +
        ticks + `<div class="now" id="now"></div>`);
      this._el.now = this.shadowRoot.getElementById("now");
      this._txt("tl-hint", `☀️ ${hh(sch.solar_start_h)}–${hh(sch.solar_end_h)} · 🌙 ${hh(sch.hc_start_h)}–${hh(sch.hc_end_h)} ${sch.winter ? "(saison hivernale : active)" : "(hors saison : inactif)"}`);
    }
    if (this._el.now) this._el.now.style.left = `calc(${(hourNow / 24) * 100}% - 1px)`;

    // Démarrage solaire
    const ck = snap.start_checks;
    const items = {
      in_solar: [ck.in_solar, `Dans la plage solaire (${hh(sch.solar_start_h)}–${hh(sch.solar_end_h)})`],
      not_done: [ck.not_done, "Cycle de chauffe pas encore terminé"],
      can_start: [ck.can_start, "Chauffe-eau à l'arrêt et redémarrage libre"],
      solar: [ck.solar, `Production > ${W(set.start_solar_w)} W (actuel : ${W(v.solar_w)} W)`],
      soc: [ck.soc, `Batterie ≥ ${W(set.start_soc)} % (actuel : ${W(v.soc)} %)`],
      surplus: [ck.surplus, `Surplus ≥ ${W(set.min_surplus_w)} W (actuel : ${W(v.surplus_w)} W)`],
    };
    const running = snap.switch === "on";
    for (const [k, [ok, label]] of Object.entries(items)) {
      const li = this._el["c-" + k];
      li.className = running ? "na" : ok ? "ok" : "";
      this._txt("c-" + k, label);
    }
    const ts = snap.timers.solar_start;
    if (running) {
      this._html("t-solar", "Chauffe-eau en marche : conditions de démarrage non évaluées.");
    } else if (ts.active) {
      const el = Math.min(ts.hold, ts.elapsed + dt);
      this._html("t-solar", `Conditions réunies depuis <b>${mmss(el)}</b> / ${mmss(ts.hold)} avant démarrage<div class="bar"><i class="warn" style="width:${(el / ts.hold) * 100}%"></i></div>`);
    } else {
      this._html("t-solar", `Le démarrage exige ${mmss(ts.hold)} de conditions stables.`);
    }

    // Sécurités
    this._timerBar("overload", "", `Import > ${W(set.max_grid_import_w)} W et maison > ${W(set.max_house_power_w)} W`, snap);
    this._timerBar("battery_low", "", `Batterie < ${W(set.stop_soc)} %`, snap);
    this._timerBar("idle", "", `Ballon < ${W(set.heater_off_w)} W`, snap);
    this._timerBar("data_lost", "", "Mesures OK", snap);

    // Journal
    const logSig = snap.events.length + "|" + (snap.events[0] ? snap.events[0].t : "");
    if (this._sig.log !== logSig) {
      this._sig.log = logSig;
      const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
      this._html("log", snap.events.length
        ? snap.events.map((ev) => {
            const d = new Date(ev.t);
            const stamp = d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }) + " " +
              d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
            return `<div class="${esc(ev.kind)}"><time>${stamp}</time><span>${esc(ev.msg)}</span></div>`;
          }).join("")
        : `<div class="empty">Aucun événement pour l'instant.</div>`);
    }

    // Réglages
    const chipSig = JSON.stringify([set, sch]);
    if (this._sig.chips !== chipSig) {
      this._sig.chips = chipSig;
      const chip = (k, val) => `<span>${k} <b>${val}</b></span>`;
      this._html("chips", [
        chip("Démarrage solaire", `> ${W(set.start_solar_w)} W`),
        chip("Surplus requis", `≥ ${W(set.min_surplus_w)} W`),
        chip("Batterie démarrage", `≥ ${W(set.start_soc)} %`),
        chip("Batterie arrêt", `< ${W(set.stop_soc)} %`),
        chip("Import anormal", `> ${W(set.max_grid_import_w)} W`),
        chip("Maison trop forte", `> ${W(set.max_house_power_w)} W`),
        chip("Ballon arrêté", `< ${W(set.heater_off_w)} W`),
        chip("Plage solaire", `${hh(sch.solar_start_h)}–${hh(sch.solar_end_h)}`),
        chip("Heures creuses", `${hh(sch.hc_start_h)}–${hh(sch.hc_end_h)} (nov.–mars)`),
      ].join(""));
    }
  }
}

customElements.define("gestion-eau-chaude-panel", GestionEauChaudePanel);
