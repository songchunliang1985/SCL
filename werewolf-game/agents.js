/* =============================================================
   Werewolf · Agent AI
   每个 agent 拥有：性格、角色、记忆、目标推断、发言生成器
   ============================================================= */

const PERSONALITIES = [
  { name: "稳健", aggro: 0.3, deception: 0.5, talkative: 0.6 },
  { name: "凶猛", aggro: 0.9, deception: 0.6, talkative: 0.9 },
  { name: "狡诈", aggro: 0.5, deception: 0.95, talkative: 0.8 },
  { name: "天真", aggro: 0.2, deception: 0.1, talkative: 0.5 },
  { name: "缜密", aggro: 0.4, deception: 0.4, talkative: 0.8 },
  { name: "锋利", aggro: 0.85, deception: 0.4, talkative: 0.85 },
  { name: "沉稳", aggro: 0.35, deception: 0.5, talkative: 0.5 },
  { name: "毒舌", aggro: 0.95, deception: 0.5, talkative: 1.0 },
  { name: "圆滑", aggro: 0.4, deception: 0.7, talkative: 0.75 },
  { name: "孤勇", aggro: 0.7, deception: 0.3, talkative: 0.7 },
  { name: "理性", aggro: 0.5, deception: 0.5, talkative: 0.75 },
  { name: "浮躁", aggro: 0.75, deception: 0.4, talkative: 0.95 },
];

const NAMES = ["阿狸","紫霞","白起","花木兰","李白","貂蝉","荆轲","韩信","程咬金","虞姬","小乔","典韦"];

const AVATARS = ["🦊","🌸","⚔️","🏹","🍶","🪭","🗡️","🐎","🪓","🌙","🎐","🛡️"];

/* ===== Agent 类 ===== */
class Agent {
  constructor(idx) {
    this.idx = idx;                  // 0..11
    this.no = idx + 1;               // 座位号 1..12
    this.name = NAMES[idx];
    this.avatar = AVATARS[idx];
    this.personality = PERSONALITIES[idx];
    this.role = null;                // wolf | seer | witch | hunter | guard | villager
    this.alive = true;

    // 角色私人信息
    this.knownWolves = [];           // 狼人队友
    this.seerChecks = [];            // [{target, isWolf, day}]
    this.witchHasSave = true;
    this.witchHasPoison = true;
    this.lastGuarded = null;         // 守卫上一晚保护对象

    // 推理与公开状态
    this.suspicion = new Array(12).fill(0); // 0~1, 高=像狼
    this.claims = {};                       // idx -> claim (例: 预言家)
    this.checkReports = [];                 // 公开声明的查验
    this.hasClaimed = false;                // 是否跳过身份
    this.publicRole = null;                 // 自己对外声称的身份
    this.isSheriff = false;
  }

  reset() {
    this.alive = true;
    this.knownWolves = [];
    this.seerChecks = [];
    this.witchHasSave = true;
    this.witchHasPoison = true;
    this.lastGuarded = null;
    this.suspicion = new Array(12).fill(0);
    this.claims = {};
    this.checkReports = [];
    this.hasClaimed = false;
    this.publicRole = null;
    this.isSheriff = false;
  }

  /* ============ 推理 ============ */
  observe(event, game) {
    // 根据事件更新怀疑度
    switch (event.type) {
      case "check-report": {
        const reporter = game.agents[event.from];
        const target = event.target;
        const result = event.result; // 'wolf' | 'good'
        if (this.role === "wolf" && this.knownWolves.includes(event.from)) break;
        if (this.role === "seer" && this.idx === event.from) break;

        if (this.role === "wolf") {
          // 真预言家对自己阵营查杀=对方真预言家
          if (result === "wolf" && this.knownWolves.includes(target)) {
            this.suspicion[event.from] = Math.max(this.suspicion[event.from], 0.95);
          }
        } else {
          // 好人视角
          const claimCount = Object.values(this.claims).filter(c => c === "seer").length;
          if (claimCount <= 1) {
            // 单跳预言家 → 高度信任
            if (result === "wolf") {
              this.suspicion[target] = Math.min(1, this.suspicion[target] + 0.75);
            } else {
              this.suspicion[target] = Math.max(0, this.suspicion[target] - 0.5);
            }
          } else {
            // 双跳，谨慎
            if (result === "wolf") {
              this.suspicion[target] = Math.min(1, this.suspicion[target] + 0.3);
              // 同时怀疑双方有一狼
              this.suspicion[event.from] = Math.min(1, this.suspicion[event.from] + 0.15);
            } else {
              this.suspicion[target] = Math.max(0, this.suspicion[target] - 0.15);
            }
          }
        }
        break;
      }
      case "claim": {
        // 跳预言家 → 标记
        const c = event.role;
        const prev = this.claims[event.from];
        if (prev && prev !== c) {
          // 改口 → 增加怀疑
          this.suspicion[event.from] = Math.min(1, this.suspicion[event.from] + 0.2);
        }
        this.claims[event.from] = c;
        break;
      }
      case "speech-suspect": {
        if (event.from === this.idx) break;
        // 别人指控的方向
        if (this.role === "wolf" && this.knownWolves.includes(event.target)) {
          this.suspicion[event.from] = Math.min(1, this.suspicion[event.from] + 0.05);
        } else {
          this.suspicion[event.target] = Math.min(1, this.suspicion[event.target] + 0.08);
        }
        break;
      }
      case "vote": {
        // 票型分析（简单）
        if (this.role === "wolf") break;
        const targetIsClaimedGod = ["seer","witch","guard","hunter"].includes(this.claims[event.target]);
        if (targetIsClaimedGod) {
          this.suspicion[event.from] = Math.min(1, this.suspicion[event.from] + 0.1);
        }
        break;
      }
      case "death-night": {
        // 夜里被刀的多半是神/预言家
        if (this.claims[event.target]) {
          // 被刀的人之前自爆身份，证实其身份概率
        }
        break;
      }
    }
  }

  /* ============ 夜晚行动 ============ */
  nightAction(game) {
    if (!this.alive) return null;
    switch (this.role) {
      case "wolf": return this._wolfKill(game);
      case "seer": return this._seerCheck(game);
      case "witch": return this._witchAct(game);
      case "guard": return this._guardProtect(game);
      default: return null;
    }
  }

  _wolfKill(game) {
    // 狼队优先刀神，其次刀疑似预言家、强发言者
    const alive = game.aliveAgents().filter(a => !this.knownWolves.includes(a.idx) && a.idx !== this.idx);
    let scored = alive.map(a => {
      let s = 0;
      if (a.publicRole === "seer") s += 100;
      if (a.publicRole === "witch") s += 40;
      if (a.publicRole === "guard") s += 35;
      if (a.publicRole === "hunter") s -= 10; // 猎人反伤，斟酌
      if (a.isSheriff) s += 30;
      s += a.personality.talkative * 15;
      s += (Math.random() - 0.5) * 10;
      return { a, s };
    });
    scored.sort((x,y) => y.s - x.s);
    return { type: "wolf-kill", target: scored[0].a.idx };
  }

  _seerCheck(game) {
    const candidates = game.aliveAgents().filter(a => a.idx !== this.idx && !this.seerChecks.some(c => c.target === a.idx));
    if (candidates.length === 0) return null;
    // 选发言激进 / 怀疑度高的
    let scored = candidates.map(a => ({
      a,
      s: this.suspicion[a.idx] * 100 + a.personality.aggro * 20 + (Math.random() - 0.5) * 30
    }));
    scored.sort((x,y) => y.s - x.s);
    return { type: "seer-check", target: scored[0].a.idx };
  }

  _witchAct(game) {
    // 救：第一晚倾向救，自己被刀有限救
    // 毒：毒掉怀疑度最高的、或预言家查杀的目标
    const actions = [];
    if (this.witchHasSave && game.tonightKill !== null) {
      const killed = game.tonightKill;
      const canSelfSave = (game.day === 1);
      const isSelf = (killed === this.idx);
      let save = false;
      if (game.day === 1) save = true; // 首夜默认救
      else if (!isSelf && this._isProbablyGod(killed, game)) save = true;
      else if (isSelf && canSelfSave) save = true;
      if (save) actions.push({ type: "witch-save", target: killed });
    }

    if (this.witchHasPoison && game.day >= 2) {
      const alive = game.aliveAgents().filter(a => a.idx !== this.idx);
      // 优先策略：场上有 ≥2 个声称预言家时，毒掉自己最怀疑的那个
      const seerClaims = alive.filter(a => a.publicRole === "seer");
      if (seerClaims.length >= 2) {
        const target = seerClaims.reduce((best, a) =>
          this.suspicion[a.idx] > this.suspicion[best.idx] ? a : best, seerClaims[0]);
        actions.push({ type: "witch-poison", target: target.idx });
      } else if (Math.random() < 0.55) {
        const target = alive.reduce((best, a) =>
          this.suspicion[a.idx] > this.suspicion[best.idx] ? a : best, alive[0]);
        if (this.suspicion[target.idx] > 0.55) {
          actions.push({ type: "witch-poison", target: target.idx });
        }
      }
    }
    return actions.length ? actions : null;
  }

  _isProbablyGod(idx, game) {
    const c = game.agents[idx].publicRole;
    if (c === "seer") return true;
    if (c === "witch" || c === "guard" || c === "hunter") return true;
    // 没跳身份但发言激进 也可能是神
    return false;
  }

  _guardProtect(game) {
    // 优先守预言家、其次守自己（但不能连守）
    const alive = game.aliveAgents();
    // 先尝试守已跳预言家
    const seer = alive.find(a => a.publicRole === "seer" && a.idx !== this.lastGuarded);
    if (seer && Math.random() < 0.75) return { type: "guard-protect", target: seer.idx };

    // 守自己（不能连守）
    if (this.lastGuarded !== this.idx && Math.random() < 0.4) {
      return { type: "guard-protect", target: this.idx };
    }
    // 守怀疑度低的发言者
    const candidates = alive.filter(a => a.idx !== this.lastGuarded);
    const target = candidates.reduce((best, a) =>
      (1 - this.suspicion[a.idx]) + a.personality.talkative > (1 - this.suspicion[best.idx]) + best.personality.talkative
        ? a : best, candidates[0]);
    return { type: "guard-protect", target: target.idx };
  }

  /* ============ 白天发言 ============ */
  generateSpeech(game) {
    const day = game.day;
    const alive = game.aliveAgents();
    const lines = [];

    // 1) 角色策略：是否跳身份
    let intent = "stay";  // stay/claim/counter-claim/vote
    let claimRole = null;
    let chartedSuspect = null;

    if (this.role === "seer" && this.seerChecks.length > 0) {
      // 默认上跳
      if (!this.hasClaimed || day >= 1) {
        intent = "claim"; claimRole = "seer";
      }
    } else if (this.role === "wolf") {
      // 狼人策略：只有第一只发言的狼且无人跳出时考虑悍跳
      const seerClaimed = game.agents.some(a => a.alive && a.publicRole === "seer");
      const otherWolfClaimedSeer = this.knownWolves.some(w => game.agents[w].publicRole === "seer");
      if (day === 1 && !seerClaimed && !otherWolfClaimedSeer && Math.random() < 0.35 * this.personality.deception) {
        intent = "claim"; claimRole = "seer";
      }
    } else if (this.role === "witch" && this.publicRole === null) {
      if (day >= 2 && Math.random() < 0.25) {
        intent = "claim"; claimRole = "witch";
      }
    } else if (this.role === "guard" && this.publicRole === null) {
      if (day >= 3 && Math.random() < 0.2) {
        intent = "claim"; claimRole = "guard";
      }
    } else if (this.role === "hunter" && this.publicRole === null) {
      if (day >= 3 && Math.random() < 0.25) {
        intent = "claim"; claimRole = "hunter";
      }
    }

    // 2) 找出怀疑对象
    const candidates = alive.filter(a => a.idx !== this.idx);
    const sorted = candidates.slice().sort((a,b) => this.suspicion[b.idx] - this.suspicion[a.idx]);
    chartedSuspect = sorted[0];

    // 狼人会指向好人（远离队友）
    if (this.role === "wolf") {
      const targets = candidates.filter(a => !this.knownWolves.includes(a.idx));
      // 优先指向跳预言家但不是真预言家的（即对方真预言家）
      const seerClaims = targets.filter(a => a.publicRole === "seer");
      if (seerClaims.length > 0) {
        chartedSuspect = seerClaims[Math.floor(Math.random() * seerClaims.length)];
      } else {
        chartedSuspect = targets[Math.floor(Math.random() * targets.length)];
      }
    }

    // 3) 拼接发言
    // 开场
    lines.push(pick([
      `各位，我是${this.no}号。`,
      `好，${this.no}号发言。`,
      `${this.no}号在此，听我一言。`,
      `轮到我了，简单说。`,
      `${this.no}号，整理一下场上信息。`,
    ]));

    // 跳身份
    if (intent === "claim") {
      this.hasClaimed = true;
      this.publicRole = claimRole;
      if (claimRole === "seer") {
        // 真假预言家都会报查验
        let checkTarget, result;
        if (this.role === "seer" && this.seerChecks.length > 0) {
          const lastCheck = this.seerChecks[this.seerChecks.length - 1];
          checkTarget = lastCheck.target;
          result = lastCheck.isWolf ? "wolf" : "good";
        } else {
          // 狼人悍跳：随机一个查杀好人
          const goodCands = candidates.filter(a => !this.knownWolves.includes(a.idx));
          checkTarget = goodCands[Math.floor(Math.random() * goodCands.length)].idx;
          result = "wolf";
        }
        const targetAgent = game.agents[checkTarget];
        if (result === "wolf") {
          lines.push(pick([
            `我是预言家，昨晚验的是 ${targetAgent.no} 号 — 查杀！`,
            `不藏了，预言家在此。${targetAgent.no} 号，狼人，明牌。`,
            `我跳预言家，${targetAgent.no} 号查杀，请大家跟我对位。`,
          ]));
        } else {
          lines.push(pick([
            `我是预言家，验的 ${targetAgent.no} 号 — 金水。`,
            `预言家报告：${targetAgent.no} 号是好人，请好人围拢。`,
          ]));
        }
        game.fireEvent({ type: "claim", from: this.idx, role: "seer" });
        game.fireEvent({ type: "check-report", from: this.idx, target: checkTarget, result });
      } else if (claimRole === "witch") {
        lines.push(pick([
          `我女巫站出来了，昨夜情况我清楚。`,
          `我是女巫，今天必须给信息了。`,
        ]));
        game.fireEvent({ type: "claim", from: this.idx, role: "witch" });
      } else if (claimRole === "guard") {
        lines.push(pick([
          `我守卫站出来澄清。`,
          `守卫在此，昨晚我守过人，下面解释。`,
        ]));
        game.fireEvent({ type: "claim", from: this.idx, role: "guard" });
      } else if (claimRole === "hunter") {
        lines.push(pick([
          `我猎人，狼人别碰我。`,
          `这局猎人是我，谁想试试我的枪？`,
        ]));
        game.fireEvent({ type: "claim", from: this.idx, role: "hunter" });
      }
    }

    // 指控
    if (chartedSuspect) {
      const reason = this._suspicionReason(chartedSuspect, game);
      lines.push(pick([
        `我重点怀疑 ${chartedSuspect.no} 号，${reason}。`,
        `${chartedSuspect.no} 号给我感觉很狼，${reason}。`,
        `站边 ${chartedSuspect.no} 号是狼，理由：${reason}。`,
        `${chartedSuspect.no} 号那波操作不对，${reason}。`,
      ]));
      game.fireEvent({ type: "speech-suspect", from: this.idx, target: chartedSuspect.idx });
    }

    // 站边/补刀
    if (this.role === "seer" && this.seerChecks.length > 0) {
      const last = this.seerChecks[this.seerChecks.length - 1];
      if (last.isWolf) {
        lines.push(`${game.agents[last.target].no} 号狼坑实锤，今天必须把他抬出去。`);
      } else {
        lines.push(`${game.agents[last.target].no} 号是金水，让他帮我站边。`);
      }
    } else if (this.role === "wolf" && this.hasClaimed && this.publicRole === "seer") {
      // 强调自己是真预言家
      lines.push(pick([
        `我才是真预言家，对面是悍跳狼。`,
        `请好人对位投我对面，今天必须把狼带走。`,
      ]));
    }

    // 收尾
    if (this.personality.talkative > 0.7) {
      lines.push(pick([
        `话说完了，过。`,
        `就这些，下一位。`,
        `今天投票别飘，跟我节奏。`,
        `我说完了，谁有问题站起来怼。`,
      ]));
    } else {
      lines.push(pick([`说完。`, `过。`, `就这些。`]));
    }

    return lines.join(" ");
  }

  _suspicionReason(target, game) {
    const reasons = [
      "发言飘忽躲位置",
      "首轮过于沉默",
      "对预言家态度暧昧",
      "票型怪异",
      "频繁打压神职",
      "气势上像悍跳",
      "夜里没死还在带节奏",
      "对位逻辑混乱",
      "情绪比信息多",
    ];
    return reasons[Math.floor(Math.random() * reasons.length)];
  }

  /* ============ 投票 ============ */
  voteTarget(game, candidates) {
    if (!this.alive) return null;
    // 狼人：投跳预言家最强威胁，避免投队友
    if (this.role === "wolf") {
      const enemies = candidates.filter(a => !this.knownWolves.includes(a.idx) && a.idx !== this.idx);
      const seer = enemies.filter(a => a.publicRole === "seer");
      if (seer.length > 0) return seer[Math.floor(Math.random() * seer.length)].idx;
      const ordered = enemies.slice().sort((a,b) => b.personality.talkative - a.personality.talkative);
      return ordered[0]?.idx ?? candidates[0].idx;
    }
    // 好人：投查杀目标，或最高怀疑度
    const checkKill = this._lastCheckKillTarget(game);
    if (checkKill !== null && candidates.some(a => a.idx === checkKill)) return checkKill;

    const ordered = candidates.filter(a => a.idx !== this.idx)
      .sort((a,b) => this.suspicion[b.idx] - this.suspicion[a.idx]);
    if (ordered.length === 0) return candidates[0].idx;
    if (ordered[0] && this.suspicion[ordered[0].idx] < 0.15) {
      // 没目标 → 弃票（用-1表示）
      return Math.random() < 0.35 ? -1 : ordered[0].idx;
    }
    return ordered[0].idx;
  }

  _lastCheckKillTarget(game) {
    // 好人会跟随真预言家的查杀
    const claimedSeers = game.agents.filter(a => a.alive && a.publicRole === "seer");
    if (claimedSeers.length === 0) return null;
    // 优先选择自己更信任的那位（怀疑度较低）
    const trusted = claimedSeers.sort((a,b) => this.suspicion[a.idx] - this.suspicion[b.idx])[0];
    const reports = game.publicCheckReports.filter(r => r.from === trusted.idx);
    const lastKill = reports.filter(r => r.result === "wolf").slice(-1)[0];
    if (lastKill && game.agents[lastKill.target].alive) return lastKill.target;
    return null;
  }
}

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
