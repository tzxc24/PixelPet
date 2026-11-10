/* Local idle behavior. Time is injected so no behavior requires a model call. */
(() => {
  class PixelPetBehavior {
    constructor({now = performance.now(), random = Math.random} = {}) {
      this.random = random;
      this.lastActivity = now;
      this.nextAction = now + 4000;
      this.wakeUntil = now;
      this.recentTouches = [];
      this.kind = 'none';
      this.ends = now;
    }

    activity(now) {
      this.lastActivity = now;
      this.nextAction = now + 4000;
      this.kind = 'none';
    }

    touch(now, double = false) {
      this.activity(now);
      this.wakeUntil = now + 20000;
      this.recentTouches = this.recentTouches.filter(time => now - time < 1800);
      this.recentTouches.push(now);
      this.recentTouches = this.recentTouches.slice(-3);
      return double || this.recentTouches.length >= 3 ? 'SHY' : 'HAPPY';
    }

    update(now, {idle, sleep = false, reduced = false}) {
      if (!idle) return {kind: 'none', lowActivity: false};
      const lowActivity = now - this.lastActivity >= 120000;
      if (sleep && now >= this.wakeUntil) return {kind: 'sleep', lowActivity: true};
      if (reduced) return {kind: 'none', lowActivity};
      if (now >= this.ends) this.kind = 'none';
      if (now >= this.nextAction) {
        const roll = this.random();
        this.kind = roll < .3 ? 'blink' : roll < .5 ? 'lookLeft' : roll < .7 ? 'lookRight' : roll < .9 ? 'sway' : 'yawn';
        this.ends = now + (this.kind === 'blink' ? 230 : 1100);
        this.nextAction = this.ends + (lowActivity ? 22000 : 4200) + this.random() * 8000;
      }
      return {kind: this.kind, lowActivity};
    }
  }

  window.PixelPetBehavior = PixelPetBehavior;
})();
