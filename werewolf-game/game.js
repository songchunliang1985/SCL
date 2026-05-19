/* =============================================================
   Werewolf · 12人神局  ——  Game Engine
   ============================================================= */

const ROLES_12 = [
  "wolf","wolf","wolf","wolf",
  "seer","witch","hunter","guard",
  "villager","villager","villager","villager",
];

const ROLE_META = {
  wolf:     { cn: "狼人",   emoji: "🐺", cls: "wolf"     },
  seer:     { cn: "预言家", emoji: "🔮", cls: "seer"     },
  witch:    { cn: "女巫",   emoji: "🧪", cls: "witch"    },
  hunter:   { cn: "猎人",   emoji: "🏹", cls: "hunter"   },
  guard:    { cn: "守卫",   emoji: "🛡️", cls: "guard"    },
  villager: { cn: "村民",   emoji: "👨‍🌾", cls: "villager" },
};

let GAME_GENERATION = 0;

class Game {
  constructor() {
    this.gen = ++GAME_GENERATION;     // 标识本局，防止旧局尾巴污染新局 UI
    this.agents = Array.from({ length: 12 }, (_, i) => new Agent(i));
    this.day = 0;
    this.phase = "idle";       // idle | night | day | vote | end
    this.tonightKill = null;   // 狼刀目标
    this.tonightSaved = false;
    this.tonightPoison = null;
    this.tonightProtected = null;
    this.publicCheckReports = []; // 公开的预言家报查
    this.history = [];
    this.running = false;
    this.paused = false;
    this.speedMs = 1200;
    this.revealAll = false;
    this.winner = null;
    this._timers = new Set();   // 本局所有 setTimeout id
  }

  isCurrent() { return this === currentGame && this.running; }

  cancel() {
    this.running = false;
    this._timers.forEach(id => clearTimeout(id));
    this._timers.clear();
  }

  /* ============ 初始化 ============ */
  reset() {
    this.day = 0;
    this.phase = "idle";
    this.tonightKill = null;
    this.tonightSaved = false;
    this.tonightPoison = null;
    this.tonightProtected = null;
    this.publicCheckReports = [];
    this.history = [];
    this.winner = null;
    this.agents.forEach(a => a.reset());
    this.assignRoles();
  }

  assignRoles() {
    // Fisher-Yates 洗牌
    const shuffled = ROLES_12.slice();
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    this.agents.forEach((a, i) => a.role = shuffled[i]);
    // 狼人互认队友
    const wolves = this.agents.filter(a => a.role === "wolf").map(a => a.idx);
    this.agents.forEach(a => {
      if (a.role === "wolf") a.knownWolves = wolves.slice();
    });
  }

  aliveAgents() { return this.agents.filter(a => a.alive); }
  aliveOf(role) { return this.aliveAgents().filter(a => a.role === role); }

  /* ============ 事件广播 ============ */
  fireEvent(evt) {
    this.agents.forEach(a => a.observe(evt, this));
    if (evt.type === "check-report") {
      this.publicCheckReports.push(evt);
    }
  }

  /* ============ 异步流程控制 ============ */
  wait(ms) {
    return new Promise(resolve => {
      const t = ms ?? this.speedMs;
      const start = performance.now();
      const tick = () => {
        if (!this.isCurrent()) { resolve(); return; }
        if (this.paused) { requestAnimationFrame(tick); return; }
        if (performance.now() - start >= t) { resolve(); return; }
        requestAnimationFrame(tick);
      };
      tick();
    });
  }

  // 受本局生命周期管理的 setTimeout，重开时自动取消
  later(fn, ms) {
    const id = setTimeout(() => {
      this._timers.delete(id);
      if (this === currentGame) fn();
    }, ms);
    this._timers.add(id);
    return id;
  }

  /* ============ 主流程 ============ */
  async run() {
    this.running = true;
    UI.bindGame(this);
    UI.renderSeats(this);
    UI.refreshAll(this);

    while (this.running && !this.winner) {
      this.day += 1;
      await this.nightPhase();
      if (this.winner) break;
      await this.dayPhase();
      if (this.winner) break;
    }

    this.phase = "end";
    UI.refreshAll(this);
    UI.showResult(this);
    this.running = false;
  }

  /* ============ 夜晚 ============ */
  async nightPhase() {
    this.phase = "night";
    document.body.classList.remove("is-day");
    UI.setPhase("night", this.day, "天黑请闭眼…");
    UI.log("night", `🌙 第 ${this.day} 天 · 夜晚降临`);
    await this.wait();

    this.tonightKill = null;
    this.tonightSaved = false;
    this.tonightPoison = null;
    this.tonightProtected = null;

    // ===== 守卫 =====
    const guard = this.aliveOf("guard")[0];
    if (guard) {
      UI.setPhase("night", this.day, "守卫请睁眼…");
      UI.activate(guard.idx);
      await this.wait();
      const act = guard.nightAction(this);
      if (act && act.target !== undefined) {
        this.tonightProtected = act.target;
        guard.lastGuarded = act.target;
        UI.drawSkillLine(guard.idx, act.target, "#4dd0a8");
        UI.markProtected(act.target);
        UI.log("skill", `🛡 守卫守护了 <span class="who">${this.agents[act.target].no}号</span>`, this.revealAll);
      }
      UI.deactivate(guard.idx);
      await this.wait();
    }

    // ===== 狼人 =====
    UI.setPhase("night", this.day, "狼人请睁眼…");
    const wolves = this.aliveOf("wolf");
    wolves.forEach(w => UI.activate(w.idx));
    await this.wait();
    if (wolves.length > 0) {
      // 投票决出击杀目标（取出现频率最高的）
      const votes = {};
      wolves.forEach(w => {
        const act = w._wolfKill(this);
        if (act) votes[act.target] = (votes[act.target] || 0) + 1;
      });
      let target = null, max = 0;
      for (const k of Object.keys(votes)) {
        if (votes[k] > max) { max = votes[k]; target = parseInt(k); }
      }
      if (target !== null) {
        this.tonightKill = target;
        UI.drawSkillLine(wolves[0].idx, target, "#ff5b6b", true);
        UI.shake(target);
        UI.log("skill", `🐺 狼人选择击杀 <span class="who">${this.agents[target].no}号</span>`, this.revealAll);
      }
    }
    wolves.forEach(w => UI.deactivate(w.idx));
    await this.wait();

    // ===== 预言家 =====
    const seer = this.aliveOf("seer")[0];
    if (seer) {
      UI.setPhase("night", this.day, "预言家请睁眼…");
      UI.activate(seer.idx);
      await this.wait();
      const act = seer.nightAction(this);
      if (act && act.target !== undefined) {
        const target = this.agents[act.target];
        const isWolf = target.role === "wolf";
        seer.seerChecks.push({ target: act.target, isWolf, day: this.day });
        UI.drawSkillLine(seer.idx, act.target, isWolf ? "#ff5b6b" : "#4ea8ff");
        UI.log("skill", `🔮 预言家查验 <span class="who">${target.no}号</span> → ${isWolf ? "🐺 狼人" : "👤 好人"}`, this.revealAll);
      }
      UI.deactivate(seer.idx);
      await this.wait();
    }

    // ===== 女巫 =====
    const witch = this.aliveOf("witch")[0];
    if (witch) {
      UI.setPhase("night", this.day, "女巫请睁眼…");
      UI.activate(witch.idx);
      await this.wait();
      const acts = witch.nightAction(this);
      if (acts) {
        for (const act of acts) {
          if (act.type === "witch-save") {
            witch.witchHasSave = false;
            this.tonightSaved = true;
            UI.drawSkillLine(witch.idx, act.target, "#4dd0a8");
            UI.log("skill", `🧪 女巫使用解药救人`, this.revealAll);
          } else if (act.type === "witch-poison") {
            witch.witchHasPoison = false;
            this.tonightPoison = act.target;
            UI.drawSkillLine(witch.idx, act.target, "#b46bff");
            UI.markPoisoned(act.target);
            UI.log("skill", `🧪 女巫使用毒药 → <span class="who">${this.agents[act.target].no}号</span>`, this.revealAll);
          }
        }
      }
      UI.deactivate(witch.idx);
      await this.wait();
    }

    // ===== 结算 =====
    UI.setPhase("night", this.day, "夜晚结算…");
    await this.wait(600);

    const deaths = [];
    if (this.tonightKill !== null) {
      if (this.tonightKill === this.tonightProtected && this.tonightSaved) {
        // 同守同救 → 死
        deaths.push(this.tonightKill);
      } else if (this.tonightKill === this.tonightProtected) {
        // 守住
      } else if (this.tonightSaved) {
        // 救活
      } else {
        deaths.push(this.tonightKill);
      }
    }
    if (this.tonightPoison !== null && !deaths.includes(this.tonightPoison)) {
      deaths.push(this.tonightPoison);
    }

    // 死亡
    deaths.forEach(idx => this.kill(idx, "night"));
    this.checkWin();
  }

  /* ============ 白天 ============ */
  async dayPhase() {
    this.phase = "day";
    document.body.classList.add("is-day");
    UI.setPhase("day", this.day, "天亮了…");
    UI.log("day", `☀️ 第 ${this.day} 天 · 白天来临`);
    await this.wait();

    // 公布死讯
    const nightDeaths = this.history.filter(h => h.day === this.day && h.cause === "night");
    if (nightDeaths.length === 0) {
      UI.log("day", `平安夜：昨晚没有人死亡。`);
      UI.setPhase("day", this.day, "平安夜");
    } else {
      const names = nightDeaths.map(d => `${this.agents[d.idx].no}号`).join("、");
      UI.log("death", `昨晚 <span class="who">${names}</span> 死亡。`);
      UI.setPhase("day", this.day, `${names} 死亡`);
      // 遗言
      for (const d of nightDeaths) {
        await this.lastWords(d.idx);
      }
      // 猎人开枪
      for (const d of nightDeaths) {
        const a = this.agents[d.idx];
        if (a.role === "hunter" && d.cause === "night" && this.tonightPoison !== d.idx) {
          await this.hunterShoot(d.idx);
        }
      }
    }
    if (this.checkWin()) return;
    await this.wait();

    // 发言阶段
    UI.setPhase("day", this.day, "依次发言…");
    const alive = this.aliveAgents();
    const startIdx = (this.day - 1) % alive.length;
    const order = alive.slice(startIdx).concat(alive.slice(0, startIdx));
    for (const a of order) {
      if (!a.alive) continue;
      await this.speak(a);
    }
    if (this.checkWin()) return;

    // 投票
    await this.votePhase();
    if (this.checkWin()) return;
  }

  async speak(agent) {
    UI.setSpeaking(agent.idx);
    UI.setPhase("day", this.day, `${agent.no}号 ${agent.name} 发言中…`);
    const text = agent.generateSpeech(this);
    UI.bubble(agent.idx, agent.name, text);
    UI.setLatestSpeech(agent, text);
    UI.log("day", `<span class="who">${agent.no}号 ${agent.name}</span>：${text}`);
    // 极速模式下也要短暂等待，便于阅读发言（最短 300ms）
    const speakMs = Math.max(300, this.speedMs * 1.2);
    await this.wait(speakMs);
    UI.clearSpeaking(agent.idx);
  }

  async lastWords(idx) {
    const agent = this.agents[idx];
    UI.markLastWords(idx);
    UI.setPhase("day", this.day, `${agent.no}号 ${agent.name} 遗言…`);
    // 死者最后发言
    let text;
    if (agent.role === "seer") {
      const checks = agent.seerChecks;
      if (checks.length > 0) {
        const last = checks[checks.length - 1];
        text = `我是预言家！${this.agents[last.target].no}号是${last.isWolf ? "🐺狼人" : "👤好人"}，请好人对位投票！`;
        // 若生前未曾跳明，此时才补一次声明事件，避免重复污染
        if (!agent.hasClaimed) {
          this.fireEvent({ type: "claim", from: idx, role: "seer" });
          this.fireEvent({ type: "check-report", from: idx, target: last.target, result: last.isWolf ? "wolf" : "good" });
        }
        agent.publicRole = "seer";
      } else {
        text = `我是预言家，可惜没来得及验人，好人小心！`;
        agent.publicRole = "seer";
        this.fireEvent({ type: "claim", from: idx, role: "seer" });
      }
    } else if (agent.role === "witch") {
      text = `我是女巫，没机会再帮你们了，跟好节奏！`;
      agent.publicRole = "witch";
      this.fireEvent({ type: "claim", from: idx, role: "witch" });
    } else if (agent.role === "guard") {
      text = `我是守卫，昨晚我守了人，狼人猖狂，好人加油！`;
      agent.publicRole = "guard";
      this.fireEvent({ type: "claim", from: idx, role: "guard" });
    } else if (agent.role === "hunter") {
      text = `我是猎人 — 准备好接受我的子弹！`;
      agent.publicRole = "hunter";
      this.fireEvent({ type: "claim", from: idx, role: "hunter" });
    } else if (agent.role === "wolf") {
      text = pick([
        `我承认我是狼，今天就这样吧。`,
        `没什么好说的，狼人继续努力。`,
        `好人多看场上信息，不要被带偏。`,
      ]);
      agent.publicRole = "wolf";
    } else {
      text = pick([
        `我就是个老百姓，可惜了。`,
        `跟好预言家，别被狼带偏！`,
        `不亏，民没什么遗憾。`,
      ]);
      agent.publicRole = "villager";
    }
    UI.bubble(idx, agent.name + "（遗言）", text);
    UI.setLatestSpeech(agent, text, true);
    UI.log("death", `<span class="who">${agent.no}号 ${agent.name} 遗言</span>：${text}`);
    await this.wait(Math.max(400, this.speedMs * 1.2));
    UI.unmarkLastWords(idx);
  }

  async hunterShoot(idx) {
    const hunter = this.agents[idx];
    // 选择最高怀疑度的活人
    const candidates = this.aliveAgents().filter(a => a.idx !== idx);
    if (candidates.length === 0) return;
    const target = candidates.reduce((best, a) =>
      hunter.suspicion[a.idx] > hunter.suspicion[best.idx] ? a : best, candidates[0]);
    UI.log("skill", `🏹 猎人开枪 → <span class="who">${target.no}号</span>`);
    UI.drawSkillLine(idx, target.idx, "#ff8b3d", true);
    UI.shake(target.idx);
    await this.wait(800);
    this.kill(target.idx, "shot");
    // 被开枪的若是猎人也开枪（链式）
    if (target.role === "hunter") {
      await this.hunterShoot(target.idx);
    }
  }

  /* ============ 投票 ============ */
  async votePhase() {
    UI.setPhase("vote", this.day, "投票阶段…");
    UI.log("vote", `🗳 进入投票阶段`);
    const candidates = this.aliveAgents();
    const tally = {};
    candidates.forEach(a => tally[a.idx] = 0);
    UI.showVoteBanner("投票开始，依次举牌…");

    for (const voter of candidates) {
      const targetIdx = voter.voteTarget(this, candidates);
      if (targetIdx === -1) {
        UI.log("vote", `<span class="who">${voter.no}号</span> 弃票`);
      } else {
        tally[targetIdx] = (tally[targetIdx] || 0) + 1;
        UI.showVoteOn(targetIdx, tally[targetIdx]);
        UI.drawSkillLine(voter.idx, targetIdx, "#ffcf6b");
        UI.log("vote", `<span class="who">${voter.no}号</span> → ${this.agents[targetIdx].no}号`);
        this.fireEvent({ type: "vote", from: voter.idx, target: targetIdx });
      }
      await this.wait(Math.min(400, this.speedMs * 0.4));
    }
    UI.showVoteBanner("");

    // 找最高票
    let maxV = 0, leaders = [];
    for (const k of Object.keys(tally)) {
      const v = tally[k], idx = parseInt(k);
      if (v > maxV) { maxV = v; leaders = [idx]; }
      else if (v === maxV && v > 0) leaders.push(idx);
    }

    if (leaders.length === 0 || maxV === 0) {
      UI.log("vote", `全员弃票，今天无人放逐。`);
    } else if (leaders.length > 1) {
      UI.log("vote", `平票，今天无人放逐。`);
    } else {
      const out = leaders[0];
      const a = this.agents[out];
      UI.log("vote", `<span class="who">${a.no}号 ${a.name}</span> 被放逐（${maxV} 票）`);
      // 遗言
      await this.lastWords(out);
      this.kill(out, "voted");
      // 猎人被投出枪
      if (a.role === "hunter") {
        await this.hunterShoot(out);
      }
    }

    this.later(() => UI.clearAllVotes(), 1500);
  }

  /* ============ 死亡 ============ */
  kill(idx, cause) {
    const a = this.agents[idx];
    if (!a.alive) return;
    a.alive = false;
    this.history.push({ idx, day: this.day, cause });
    UI.markDead(idx);
    UI.log("death", `💀 ${a.no}号 ${a.name} 倒下（${cause === "night" ? "夜晚" : cause === "shot" ? "枪杀" : "放逐"}）`);
    UI.updateAliveCounter(this);
  }

  /* ============ 胜负 ============ */
  checkWin() {
    const aliveWolves = this.aliveOf("wolf").length;
    const aliveGods = this.aliveAgents().filter(a => ["seer","witch","hunter","guard"].includes(a.role)).length;
    const aliveVillagers = this.aliveOf("villager").length;
    if (aliveWolves === 0) {
      this.winner = "good";
      UI.log("win", `🎉 好人阵营胜利！`);
      return true;
    }
    if (aliveGods === 0 || aliveVillagers === 0) {
      this.winner = "wolf";
      UI.log("win", `🐺 狼人阵营胜利！（${aliveGods === 0 ? "屠神" : "屠民"}）`);
      return true;
    }
    return false;
  }
}

/* =============================================================
   UI · 渲染层
   ============================================================= */
const UI = {
  seatsEl: null, logEl: null, fxLayer: null, bubbleLayer: null,
  centerEmoji: null, centerDay: null, centerStatus: null,
  phaseIcon: null, phaseText: null, phaseDay: null,
  voteBanner: null, latestSpeech: null,
  game: null,

  init() {
    this.seatsEl = document.getElementById("seats");
    this.logEl = document.getElementById("log");
    this.fxLayer = document.getElementById("fxLayer");
    this.bubbleLayer = document.getElementById("bubbleLayer");
    this.centerEmoji = document.getElementById("centerEmoji");
    this.centerDay = document.getElementById("centerDay");
    this.centerStatus = document.getElementById("centerStatus");
    this.phaseIcon = document.getElementById("phaseIcon");
    this.phaseText = document.getElementById("phaseText");
    this.phaseDay = document.getElementById("phaseDay");
    this.voteBanner = document.getElementById("voteBanner");
    this.latestSpeech = document.getElementById("latestSpeech");
  },

  bindGame(g) { this.game = g; },

  /* ============ 座位渲染 ============ */
  renderSeats(game) {
    this.seatsEl.innerHTML = "";
    // 清空残留的特效层与气泡层，避免坐标错位
    if (this.fxLayer) this.fxLayer.innerHTML = "";
    if (this.bubbleLayer) this.bubbleLayer.innerHTML = "";

    const N = 12;
    const wrap = document.querySelector(".table-wrap");
    const rect = wrap.getBoundingClientRect();
    const cx = rect.width / 2, cy = rect.height / 2;
    // 半径根据中央光环 (120px) 自适应，避免座位贴中央
    const minDim = Math.min(rect.width, rect.height);
    const rx = Math.max(minDim * 0.40, 160);
    const ry = Math.max(minDim * 0.36, 150);

    game.agents.forEach((a, i) => {
      // 顶部为1号，顺时针
      const angle = (-90 + (360 / N) * i) * Math.PI / 180;
      const x = cx + rx * Math.cos(angle);
      const y = cy + ry * Math.sin(angle);
      const seat = document.createElement("div");
      seat.className = "seat";
      seat.id = `seat-${a.idx}`;
      seat.style.left = x + "px";
      seat.style.top = y + "px";
      seat.innerHTML = `
        <div class="avatar">
          <span class="seat-no">${a.no}</span>
          <span class="emoji">${a.avatar}</span>
          <div class="badges"></div>
          <div class="votes" id="vote-${a.idx}">0</div>
        </div>
        <div class="name">${a.name}</div>
        <div class="role-tag" id="role-${a.idx}">${a.personality.name}</div>
      `;
      this.seatsEl.appendChild(seat);

      // 还原状态（应对窗口缩放重新渲染）
      if (!a.alive) {
        seat.classList.add("dead");
        this.revealRole(a);
      } else if (game.revealAll) {
        this.revealRole(a);
      }
    });
    // FX layer 设置尺寸
    this.fxLayer.setAttribute("viewBox", `0 0 ${rect.width} ${rect.height}`);
    this.fxLayer.setAttribute("width", rect.width);
    this.fxLayer.setAttribute("height", rect.height);
  },

  refreshAll(game) {
    this.updateAliveCounter(game);
    if (game.revealAll || game.phase === "end") {
      game.agents.forEach(a => this.revealRole(a));
    }
  },

  revealRole(a) {
    const el = document.getElementById(`role-${a.idx}`);
    if (!el || !a.role) return;
    const meta = ROLE_META[a.role];
    el.textContent = meta.emoji + " " + meta.cn;
    el.className = "role-tag show " + meta.cls;
  },

  showPersonality(a) {
    const el = document.getElementById(`role-${a.idx}`);
    if (!el) return;
    el.textContent = a.personality.name;
    el.className = "role-tag";
  },

  /* ============ 阶段提示 ============ */
  setPhase(phase, day, status) {
    const map = {
      idle: ["🌙", "准备开始"],
      night: ["🌙", "夜晚"],
      day: ["☀️", "白天"],
      vote: ["🗳", "投票"],
      end: ["🏁", "结束"],
    };
    const [icon, text] = map[phase] || map.idle;
    this.phaseIcon.textContent = icon;
    this.phaseText.textContent = text;
    this.phaseDay.textContent = `第 ${day} 天`;
    this.centerEmoji.textContent = icon;
    this.centerDay.textContent = `第 ${day} 天`;
    this.centerStatus.textContent = status || "";
  },

  /* ============ 座位状态 ============ */
  activate(idx) { document.getElementById(`seat-${idx}`)?.classList.add("active"); },
  deactivate(idx) { document.getElementById(`seat-${idx}`)?.classList.remove("active"); },
  setSpeaking(idx) {
    document.querySelectorAll(".seat.speaking").forEach(el => el.classList.remove("speaking"));
    document.getElementById(`seat-${idx}`)?.classList.add("speaking");
  },
  clearSpeaking(idx) { document.getElementById(`seat-${idx}`)?.classList.remove("speaking"); },
  shake(idx) {
    const el = document.getElementById(`seat-${idx}`);
    if (!el) return;
    el.classList.add("targeted");
    this.game.later(() => el.classList.remove("targeted"), 1200);
  },
  markProtected(idx) {
    const el = document.getElementById(`seat-${idx}`);
    if (!el) return;
    el.classList.add("protected");
    this.game.later(() => el.classList.remove("protected"), 1500);
  },
  markPoisoned(idx) {
    const el = document.getElementById(`seat-${idx}`);
    if (!el) return;
    el.classList.add("poisoned");
    this.game.later(() => el.classList.remove("poisoned"), 1500);
  },
  markLastWords(idx) { document.getElementById(`seat-${idx}`)?.classList.add("last-words"); },
  unmarkLastWords(idx) { document.getElementById(`seat-${idx}`)?.classList.remove("last-words"); },
  markDead(idx) {
    const el = document.getElementById(`seat-${idx}`);
    if (!el) return;
    el.classList.add("dead");
    el.classList.remove("speaking","active","last-words","protected","poisoned","targeted");
    // 暴露身份
    const a = this.game.agents[idx];
    this.revealRole(a);
  },

  /* ============ 技能特效线 ============ */
  drawSkillLine(fromIdx, toIdx, color, withArrow = false) {
    const wrap = document.querySelector(".table-wrap");
    const rect = wrap.getBoundingClientRect();
    const a = document.querySelector(`#seat-${fromIdx} .avatar`);
    const b = document.querySelector(`#seat-${toIdx} .avatar`);
    if (!a || !b) return;
    const ar = a.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    const x1 = ar.left + ar.width / 2 - rect.left;
    const y1 = ar.top  + ar.height / 2 - rect.top;
    const x2 = br.left + br.width / 2 - rect.left;
    const y2 = br.top  + br.height / 2 - rect.top;

    const ns = "http://www.w3.org/2000/svg";
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", x1); line.setAttribute("y1", y1);
    line.setAttribute("x2", x2); line.setAttribute("y2", y2);
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "3");
    line.setAttribute("opacity", "0.9");
    line.setAttribute("class", "fx-line");
    line.style.filter = `drop-shadow(0 0 6px ${color})`;
    this.fxLayer.appendChild(line);
    this.game.later(() => line.remove(), 1500);

    // 端点亮点
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", x2); dot.setAttribute("cy", y2);
    dot.setAttribute("r", "8"); dot.setAttribute("fill", color);
    dot.setAttribute("opacity", "0.6");
    dot.style.filter = `drop-shadow(0 0 8px ${color})`;
    this.fxLayer.appendChild(dot);
    this.game.later(() => dot.remove(), 1500);
  },

  /* ============ 发言气泡 ============ */
  bubble(idx, who, text) {
    const wrap = document.querySelector(".table-wrap");
    const rect = wrap.getBoundingClientRect();
    const a = document.querySelector(`#seat-${idx} .avatar`);
    if (!a) return;
    const ar = a.getBoundingClientRect();
    const cx = ar.left + ar.width / 2 - rect.left;
    // 圆桌下半的座位，气泡向下显示，避免被中央光环挡住
    const seatTop = ar.top - rect.top;
    const isLower = seatTop > rect.height * 0.55;
    const topY = isLower ? (ar.bottom - rect.top + 16) : (seatTop - 100);

    const el = document.createElement("div");
    el.className = "bubble" + (isLower ? " bubble-below" : "");
    el.innerHTML = `<div class="who">${who}</div>${text}`;
    this.bubbleLayer.appendChild(el);
    // 测量后 clamp 到容器内
    const bw = 220, bh = 90;
    let left = cx - bw / 2;
    left = Math.max(8, Math.min(rect.width - bw - 8, left));
    let top  = Math.max(8, Math.min(rect.height - bh - 8, topY));
    el.style.left = left + "px";
    el.style.top  = top  + "px";

    this.game.later(() => {
      el.style.transition = "opacity 0.5s, transform 0.5s";
      el.style.opacity = "0";
      el.style.transform = "translateY(-10px)";
    }, 3200);
    this.game.later(() => el.remove(), 3800);
  },

  setLatestSpeech(agent, text, isLast = false) {
    this.latestSpeech.innerHTML = `<span class="speaker">${agent.no}号 ${agent.name}${isLast ? "（遗言）" : ""}：</span>${text}`;
  },

  /* ============ 投票 ============ */
  showVoteBanner(text) {
    if (!text) { this.voteBanner.classList.remove("show"); return; }
    this.voteBanner.textContent = text;
    this.voteBanner.classList.add("show");
  },
  showVoteOn(idx, count) {
    const el = document.getElementById(`vote-${idx}`);
    if (!el) return;
    el.textContent = count;
    el.classList.add("show");
  },
  clearAllVotes() {
    document.querySelectorAll(".votes").forEach(el => {
      el.classList.remove("show");
      el.textContent = "0";
    });
  },

  /* ============ 日志 ============ */
  log(type, html, alsoCenter = false) {
    const e = document.createElement("div");
    e.className = "log-entry " + type;
    const tagMap = {
      night: "夜", day: "昼", death: "亡", skill: "技", vote: "投", win: "胜",
    };
    e.innerHTML = `<span class="tag">${tagMap[type] || ""}</span>${html}`;
    this.logEl.appendChild(e);
    this.logEl.scrollTop = this.logEl.scrollHeight;
    if (alsoCenter) this.centerStatus.textContent = html.replace(/<[^>]+>/g, "");
  },

  /* ============ 计数 ============ */
  updateAliveCounter(game) {
    const wolves = game.aliveOf("wolf").length;
    const good = game.aliveAgents().length - wolves;
    document.getElementById("aliveGood").textContent = good;
    document.getElementById("aliveBad").textContent = wolves;
  },

  /* ============ 结算面板 ============ */
  showResult(game) {
    const overlay = document.getElementById("resultOverlay");
    const emoji = document.getElementById("resultEmoji");
    const title = document.getElementById("resultTitle");
    const subtitle = document.getElementById("resultSubtitle");
    const roles = document.getElementById("resultRoles");

    if (game.winner === "good") {
      emoji.textContent = "🏆";
      title.textContent = "好人阵营胜利";
      subtitle.textContent = "真相大白，狼患平定";
    } else {
      emoji.textContent = "🐺";
      title.textContent = "狼人阵营胜利";
      subtitle.textContent = "屠刀已悬，村庄沦陷";
    }
    roles.innerHTML = "";
    game.agents.forEach(a => {
      const m = ROLE_META[a.role];
      const d = document.createElement("div");
      d.className = "rrow";
      d.innerHTML = `<span class="rno">${a.no}号</span> ${a.name} ${m.emoji}<span class="rrl">${m.cn}${a.alive ? "" : " · 已亡"}</span>`;
      roles.appendChild(d);
    });
    overlay.classList.remove("hidden");
  },

  hideResult() {
    document.getElementById("resultOverlay").classList.add("hidden");
  },
};

/* =============================================================
   启动绑定
   ============================================================= */
let currentGame = null;

function startNewGame() {
  UI.hideResult();
  if (currentGame) currentGame.cancel();
  // 复位暂停按钮文字
  const btnPause = document.getElementById("btnPause");
  if (btnPause) btnPause.textContent = "⏸ 暂停";
  // 复位昼夜背景
  document.body.classList.remove("is-day");

  currentGame = new Game();
  currentGame.reset();
  currentGame.speedMs = parseInt(document.getElementById("speedSel").value);
  currentGame.revealAll = document.getElementById("revealRoles").checked;
  UI.bindGame(currentGame);
  UI.renderSeats(currentGame);
  UI.refreshAll(currentGame);
  UI.clearAllVotes();
  // 初始日志
  document.getElementById("log").innerHTML = "";
  document.getElementById("latestSpeech").innerHTML = "—— 等待开局 ——";
  UI.log("day", "—— 新的一局开始，12位玩家入场 ——");
  currentGame.run();
}

window.addEventListener("DOMContentLoaded", () => {
  UI.init();

  // 占位渲染
  const placeholder = new Game();
  placeholder.assignRoles();
  UI.bindGame(placeholder);
  UI.renderSeats(placeholder);

  document.getElementById("btnStart").addEventListener("click", startNewGame);
  document.getElementById("btnPause").addEventListener("click", e => {
    if (!currentGame) return;
    currentGame.paused = !currentGame.paused;
    e.target.textContent = currentGame.paused ? "▶ 继续" : "⏸ 暂停";
  });
  document.getElementById("btnReset").addEventListener("click", startNewGame);
  document.getElementById("btnPlayAgain").addEventListener("click", startNewGame);
  document.getElementById("speedSel").addEventListener("change", e => {
    if (currentGame) currentGame.speedMs = parseInt(e.target.value);
  });
  document.getElementById("revealRoles").addEventListener("change", e => {
    if (currentGame) {
      currentGame.revealAll = e.target.checked;
      if (e.target.checked) currentGame.agents.forEach(a => UI.revealRole(a));
      else currentGame.agents.forEach(a => { if (a.alive) UI.showPersonality(a); });
    }
  });
  window.addEventListener("resize", () => {
    if (currentGame) UI.renderSeats(currentGame);
    else { UI.renderSeats(placeholder); }
  });
});
