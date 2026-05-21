/* =============================================================
   Werewolf · TTS (Text-to-Speech) Module
   ============================================================= */
/* 独立的语音合成模块，从 game.js 抽离。

   依赖（最小化）：
   - Web Speech API（speechSynthesis、SpeechSynthesisUtterance）
   - DOM：document.getElementById/querySelectorAll（仅用于 seat 高亮 CSS）
   - agent 对象的：idx、personality.aggro、personality.talkative

   暴露：
   - 全局 const TTS = { enabled, available, init, speak, pause, resume, stop }
   - TTS._internals（性别表、voice 模式、纯函数）—— 供测试 / 外部工具按需访问

   策略：
   - 12 个 agent 按 GENDERS 表分两组 voice
   - 同性别组内按 idx 顺序轮转分配 voice
   - pitch = 性别基线 + 组内偏移（让同性别不撞声）+ aggro 微调
   - rate = 0.85 + talkative * 0.45
*/

const TTS = (function () {

  // ── 配置：可调，独立于运行时逻辑 ──

  // 12 agent 性别表（idx 顺序与 web/agents.js 的 NAMES 一致）
  //   F=阿狸 紫霞    花木兰    貂蝉 荆轲       虞姬 小乔
  //   M=        白起     李白         韩信 程咬金        典韦
  const GENDERS = ["F","F","M","F","M","F","F","M","M","F","F","M"];

  // 中文 voice 名字匹配模式（优先 Microsoft Online Natural voice，兜底旧 voice）
  // 女声 9 个：Xiaoxiao / Xiaoyi / Yunxia / Xiaobei / HsiaoChen / HsiaoYu / Xiaoni / HiuGaai / HiuMaan
  // 男声 5 个：WanLung / Yunjian / Yunxi / Yunyang / YunJhe
  const VOICE_PATTERNS = {
    F: /Xiaoxiao|Xiaoyi|Yunxia|Xiaobei|HsiaoChen|HsiaoYu|Xiaoni|HiuGaai|HiuMaan|Huihui|Yaoyao|Female/i,
    M: /WanLung|Yunjian|Yunxi|Yunyang|YunJhe|Kangkang|Male/i,
  };

  // 性别相关的 pitch 基线 + 偏移范围（F 声更高、M 声更低；range 控制同性别组内差异）
  const PITCH_PARAMS = {
    F: { base: 1.10, range: 0.40 },
    M: { base: 0.70, range: 0.30 },
  };

  const SPEAK_TIMEOUT_MS = 15000;

  // ── 纯函数（可测试，无副作用）──

  // 计算 agent 在自己性别组内的位次（用于 voice 轮转和 pitch 偏移）
  function genderOrder(idx) {
    const gender = GENDERS[idx];
    const sameGender = GENDERS.reduce((acc, g, i) => {
      if (g === gender) acc.push(i);
      return acc;
    }, []);
    return { gender, orderInGender: sameGender.indexOf(idx), count: sameGender.length };
  }

  // 根据 agent 计算 SpeechSynthesisUtterance 的 pitch / rate
  function computeParams(agent) {
    const { gender, orderInGender, count } = genderOrder(agent.idx);
    const { base, range } = PITCH_PARAMS[gender];
    const norm = (count > 1) ? (orderInGender / (count - 1) - 0.5) : 0;
    const groupOffset = norm * range;
    const aggroAdjust = (0.5 - agent.personality.aggro) * 0.15;
    const pitch = Math.max(0.5, Math.min(1.5, base + groupOffset + aggroAdjust));
    const rate  = 0.85 + agent.personality.talkative * 0.45;
    return { pitch: +pitch.toFixed(2), rate: +rate.toFixed(2) };
  }

  // ── TTS 单例 ──

  const tts = {
    enabled: false,
    available: typeof speechSynthesis !== "undefined",
    voicesF: [],
    voicesM: [],
    voicesAny: [],

    init() {
      if (!this.available) return;
      const refresh = () => {
        const all = speechSynthesis.getVoices();
        this.voicesAny = all.filter(v => /^zh/i.test(v.lang));
        if (this.voicesAny.length === 0) this.voicesAny = all;
        this.voicesF = this.voicesAny.filter(v => VOICE_PATTERNS.F.test(v.name));
        this.voicesM = this.voicesAny.filter(v => VOICE_PATTERNS.M.test(v.name));
        // 未标性别的中文 voice：按出现顺序兜底分配，让 F/M 池均衡
        this.voicesAny.forEach(v => {
          if (!this.voicesF.includes(v) && !this.voicesM.includes(v)) {
            if (this.voicesF.length <= this.voicesM.length) this.voicesF.push(v);
            else this.voicesM.push(v);
          }
        });
        console.log(`[TTS] voices loaded: ${this.voicesAny.length} zh voices (F=${this.voicesF.length} M=${this.voicesM.length})`);
      };
      refresh();
      speechSynthesis.addEventListener("voiceschanged", refresh);
    },

    // 内部：根据 agent 在自己性别 voice 池里选一个
    _pickVoice(agent) {
      const { gender, orderInGender } = genderOrder(agent.idx);
      const pool = gender === "F" ? this.voicesF : this.voicesM;
      if (pool.length === 0) return this.voicesAny[0] || null;
      return pool[orderInGender % pool.length];
    },

    speak(text, agent) {
      if (!this.enabled || !this.available) return Promise.resolve();
      return new Promise(resolve => {
        try { speechSynthesis.cancel(); } catch {}
        const seat = document.getElementById(`seat-${agent.idx}`);
        let finished = false;
        const done = () => {
          if (finished) return;
          finished = true;
          seat?.classList.remove("tts-active");
          resolve();
        };
        const u = new SpeechSynthesisUtterance(text);
        u.lang = "zh-CN";
        const v = this._pickVoice(agent);
        if (v) u.voice = v;
        const { pitch, rate } = computeParams(agent);
        u.pitch  = pitch;
        u.rate   = rate;
        u.volume = 1;
        u.onend   = done;
        u.onerror = done;
        seat?.classList.add("tts-active");
        speechSynthesis.speak(u);
        setTimeout(done, SPEAK_TIMEOUT_MS);
      });
    },

    pause()  { if (this.available) speechSynthesis.pause();  },
    resume() { if (this.available) speechSynthesis.resume(); },
    stop() {
      if (this.available) { try { speechSynthesis.cancel(); } catch {} }
      document.querySelectorAll(".seat.tts-active").forEach(el => el.classList.remove("tts-active"));
    },
  };

  // 暴露纯函数 + 配置给测试 / 外部工具
  tts._internals = { GENDERS, VOICE_PATTERNS, PITCH_PARAMS, genderOrder, computeParams };

  return tts;
})();

// 兼容 verify 脚本 / Node vm 环境：把 TTS 挂到 globalThis（浏览器顶层 const 已经全局可见）
if (typeof window !== "undefined") window.TTS = TTS;
