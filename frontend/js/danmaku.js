/**
 * Danmaku (bullet chat) — canvas-based overlay.
 *
 * Usage:
 *   const d = new Danmaku(document.querySelector('.player-wrapper'));
 *   d.start();
 *   d.send('Hello!');
 *   d.stop();
 */
class Danmaku {
  /**
   * @param {HTMLElement} container  The element that holds the video.
   *        Must be position:relative (or similar) so the canvas overlays it.
   */
  constructor(container) {
    this.container = container;

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'danmaku-canvas';
    this.canvas.style.cssText =
      'position:absolute;top:0;left:0;width:100%;height:100%;' +
      'pointer-events:none;z-index:10;';
    container.appendChild(this.canvas);

    this.ctx = this.canvas.getContext('2d');
    /** @type {{text:string;color:string;x:number;y:number;speed:number;fontSize:number}[]} */
    this.items = [];
    this.running = false;
    this.lastTime = 0;
    this._resize = this._onResize.bind(this);
    window.addEventListener('resize', this._resize);
    this._onResize();
  }

  /* ── Internal ────────────────────────────────────────────────────────── */

  _onResize() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    this.canvas.width = w;
    this.canvas.height = h;
    this._w = w;
    this._h = h;
  }

  /* ── Lifecycle ───────────────────────────────────────────────────────── */

  start() {
    if (this.running) return;
    this.running = true;
    this.lastTime = performance.now();
    this._loop();
  }

  stop() {
    this.running = false;
    this.ctx.clearRect(0, 0, this._w, this._h);
  }

  destroy() {
    this.stop();
    window.removeEventListener('resize', this._resize);
    if (this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
  }

  /* ── Public API ──────────────────────────────────────────────────────── */

  /**
   * @param {string} text
   * @param {string} [color='#FFFFFF']
   */
  send(text, color = '#FFFFFF') {
    if (!this._w) return;
    this.items.push({
      text,
      color,
      x: this._w,
      y: 20 + Math.random() * (this._h - 60),
      speed: 120 + Math.random() * 100, // px/sec
      fontSize: 18 + Math.random() * 8,
    });
  }

  /* ── Render loop ─────────────────────────────────────────────────────── */

  _loop() {
    if (!this.running) return;

    const now = performance.now();
    const dt = Math.min((now - this.lastTime) / 1000, 0.05); // cap dt to 50ms
    this.lastTime = now;

    const ctx = this.ctx;
    ctx.clearRect(0, 0, this._w, this._h);

    for (let i = this.items.length - 1; i >= 0; i--) {
      const it = this.items[i];
      it.x -= it.speed * dt;

      // Measure text width to know when it's fully off-screen
      ctx.font = `bold ${it.fontSize}px "Segoe UI","Microsoft YaHei",sans-serif`;
      const tw = ctx.measureText(it.text).width;
      if (it.x + tw < 0) {
        this.items.splice(i, 1);
        continue;
      }

      ctx.shadowColor = 'rgba(0,0,0,0.85)';
      ctx.shadowBlur = 6;
      ctx.fillStyle = it.color;
      ctx.font = `bold ${it.fontSize}px "Segoe UI","Microsoft YaHei",sans-serif`;
      ctx.textBaseline = 'middle';
      ctx.fillText(it.text, it.x, it.y);
      ctx.shadowBlur = 0;
    }

    requestAnimationFrame(() => this._loop());
  }
}
