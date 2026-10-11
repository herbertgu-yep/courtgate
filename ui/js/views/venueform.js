/* 新建 / 编辑场馆：营业时间 → 休息窗口 / 高峰时段（区间联动约束）→ 粒度 → 场地 */
window.VIEWS = window.VIEWS || {};
VIEWS.venueform = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">{{ isEdit ? "编辑场馆" : "新建场馆" }}</div>
        <div class="ts">{{ isEdit ? "配置与价格变更仅对之后放场的批次生效，已有预约不受影响" : "保存后可对该场馆放场" }}</div></div>
    </div>
    <div class="form-card glass">
      <label class="fl">场馆名称</label>
      <input v-model="f.name" maxlength="50" placeholder="如：星羽羽毛球馆">
      <label class="fl">地址</label>
      <input v-model="f.address" maxlength="100" placeholder="如：高新区体育路 1 号">
      <label class="fl">联系电话</label>
      <input v-model="f.phone" maxlength="20" placeholder="选填">

      <label class="fl">营业时间（先定营业区间，休息与高峰只能落在其中）</label>
      <div class="cap-row">
        <select v-model="f.open_time">
          <option v-for="o in openOpts" :key="o.v" :value="o.v" :disabled="o.disabled">{{ o.v }}</option>
        </select>
        <select v-model="f.close_time">
          <option v-for="o in closeOpts" :key="o.v" :value="o.v" :disabled="o.disabled">{{ o.v }}</option>
        </select>
      </div>

      <label class="fl">中途休息窗口（如午休，可加多个；不可与营业区间外、彼此或高峰重叠）</label>
      <div class="cap-row" v-for="(b, i) in f.breaks" :key="i" style="margin-bottom:8px">
        <select v-model="b.start">
          <option v-for="o in breakStartOpts(i)" :key="o.v" :value="o.v" :disabled="o.disabled">{{ o.v }}</option>
        </select>
        <select v-model="b.end">
          <option v-for="o in breakEndOpts(i)" :key="o.v" :value="o.v" :disabled="o.disabled">{{ o.v }}</option>
        </select>
        <button class="bk-btn line" @click="f.breaks.splice(i, 1)">删除</button>
      </div>
      <button class="bk-btn line" v-if="f.breaks.length < 4" @click="addBreak">+ 添加休息窗口</button>

      <label class="fl">高峰时段（选填：窗口内开始的时段按倍率计价；不可与休息重叠）</label>
      <template v-if="f.peak_start">
        <div class="cap-row">
          <select v-model="f.peak_start">
            <option v-for="o in peakStartOpts" :key="o.v" :value="o.v" :disabled="o.disabled">{{ o.v }}</option>
          </select>
          <select v-model="f.peak_end">
            <option v-for="o in peakEndOpts" :key="o.v" :value="o.v" :disabled="o.disabled">{{ o.v }}</option>
          </select>
          <select v-model.number="f.peak_ratio_bp" style="flex:0 0 96px">
            <option :value="12500">×1.25</option>
            <option :value="15000">×1.5</option>
            <option :value="20000">×2</option>
          </select>
        </div>
        <button class="bk-btn line" style="margin-top:8px" @click="f.peak_start = ''; f.peak_end = ''">移除高峰</button>
      </template>
      <button class="bk-btn line" v-else @click="addPeak">+ 添加高峰时段</button>

      <label class="fl">一次预约时段时长</label>
      <select v-model="f.slot_minutes">
        <option :value="30">30 分钟</option>
        <option :value="60">60 分钟</option>
        <option :value="90">90 分钟</option>
        <option :value="120">120 分钟</option>
      </select>
      <div class="muted" style="margin-top:6px" v-if="preview.length">
        将切出 {{ preview.length }} 个时段：{{ preview[0].start }}–{{ preview[preview.length - 1].end }}{{ peakText }}</div>
      <div class="err-box" v-if="conflict">{{ conflict }}</div>

      <template v-if="!isEdit">
        <label class="fl">场地数量</label>
        <input v-model.number="f.court_count" type="number" min="1" max="99" placeholder="如：6">
        <label class="fl">场地单价（元 / 时段，高峰时段按上方倍率上浮）</label>
        <input v-model.number="priceYuan" type="number" min="1" placeholder="如：30">
      </template>
      <template v-else>
        <label class="fl">场地（名称与单价可改；新增场地保存后立即可用于放场）</label>
        <div class="cap-row" v-for="(c, i) in courts" :key="c.id || 'new' + i" style="margin-bottom:8px">
          <input v-model="c.name" maxlength="30" style="flex:1" :disabled="c.status === 'inactive'">
          <input v-model.number="c.priceYuan" type="number" min="1" style="flex:0 0 100px"
                 :disabled="c.status === 'inactive'">
          <span class="tag cancel" v-if="c.status === 'inactive'">已删除</span>
          <span class="tag sand" v-else-if="c.isNew">新</span>
          <button class="bk-btn line" v-if="c.id && c.status !== 'inactive'" @click="removeCourt(i)">删除</button>
        </div>
        <button class="bk-btn line" @click="addCourt">+ 新增场地</button>
        <div class="muted" style="margin-top:8px">${ICONS.info} 已有批次的时段价格在放场时固化：改配置后需重新放场，或在放场页对未产生预约的批次「重生成时段」。</div>
      </template>

      <label class="fl">场馆公告</label>
      <input v-model="f.notice" maxlength="200" placeholder="如：预约后 15 分钟内完成支付">
      <div class="err-box" v-if="err">{{ err }}</div>
      <div class="ok-box" v-if="ok">{{ ok }}</div>
      <button class="big-cta" @click="submit" :disabled="busy || !!conflict" style="margin-top:14px">
        {{ busy ? "保存中…" : isEdit ? "保存修改" : "创建场馆" }}</button>
    </div>
  </div>`,
  data: () => ({
    isEdit: false, venueId: 0, courts: [],
    f: { name: "", address: "", phone: "", open_time: "08:00", close_time: "22:00",
         breaks: [], slot_minutes: 60, peak_start: "", peak_end: "", peak_ratio_bp: 15000,
         notice: "", court_count: 4, base_price_cents: 3000 },
    err: "", ok: "", busy: false,
  }),
  computed: {
    priceYuan: {
      get() { return this.f.base_price_cents / 100; },
      set(v) { this.f.base_price_cents = Math.round((Number(v) || 0) * 100); },
    },
    // 30 分钟粒度时间轴
    grid() {
      const out = [];
      for (let m = 0; m < 24 * 60; m += 30) {
        out.push(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
      }
      return out;
    },
    hm() {
      return s => { const [h, m] = String(s || "").split(":").map(Number); return (h || 0) * 60 + (m || 0); };
    },
    openM() { return this.hm(this.f.open_time); },
    closeM() { return this.hm(this.f.close_time); },
    openOpts() {
      return this.grid.map(v => ({ v, disabled: this.hm(v) >= this.closeM }));
    },
    closeOpts() {
      return this.grid.map(v => ({ v, disabled: this.hm(v) <= this.openM }));
    },
    peakMult() {
      const bp = Number(this.f.peak_ratio_bp) || 15000;
      return String(bp / 10000).replace(/0+$/, "").replace(/\.$/, "") || "1";
    },
    peakText() {
      if (!this.f.peak_start || !this.f.peak_end) return "，全时段统一价";
      return `，高峰 ${this.f.peak_start}–${this.f.peak_end} ×${this.peakMult}`;
    },
    // 当前配置是否互相冲突（区间关系被破坏时阻止保存并说明）
    conflict() {
      if (this.openM >= this.closeM) return "营业开始时间必须早于结束时间";
      for (const b of this.f.breaks) {
        if (!b.start || !b.end) return "休息窗口需填写完整";
        if (this.hm(b.start) < this.openM || this.hm(b.end) > this.closeM) return "休息窗口必须落在营业时间内";
      }
      for (let i = 0; i < this.f.breaks.length; i++) {
        for (let j = i + 1; j < this.f.breaks.length; j++) {
          if (this.overlap(this.f.breaks[i], this.f.breaks[j])) return "休息窗口之间不能重叠";
        }
      }
      if (this.f.peak_start) {
        if (!this.f.peak_end) return "高峰时段需填写结束时间";
        if (this.hm(this.f.peak_start) < this.openM || this.hm(this.f.peak_end) > this.closeM) {
          return "高峰时段必须落在营业时间内";
        }
        for (const b of this.f.breaks) {
          if (this.overlap(b, { start: this.f.peak_start, end: this.f.peak_end })) {
            return "高峰时段与休息窗口不能重叠";
          }
        }
      }
      return "";
    },
    peakStartOpts() {
      return this.grid.map(v => {
        const t = this.hm(v);
        let disabled = t < this.openM || t >= this.closeM;
        if (!disabled) disabled = this.f.breaks.some(b => this.overlap({ start: v, end: this.fm(t + 30) }, b));
        return { v, disabled };
      });
    },
    peakEndOpts() {
      const ps = this.hm(this.f.peak_start);
      return this.grid.map(v => {
        const t = this.hm(v);
        let disabled = t <= ps || t > this.closeM;
        if (!disabled) disabled = this.f.breaks.some(b => this.overlap({ start: this.fm(ps), end: v }, b));
        return { v, disabled };
      });
    },
    // 前端本地预览切片数量（以后端校验为准）
    preview() {
      const brs = this.f.breaks.filter(b => b.start && b.end).map(b => [this.hm(b.start), this.hm(b.end)]);
      const step = Number(this.f.slot_minutes) || 60;
      const out = []; let cur = this.openM;
      while (cur + step <= this.closeM) {
        const hit = brs.find(w => cur < w[1] && cur + step > w[0]);
        if (hit) { cur = hit[1]; continue; }
        out.push({ start: this.fm(cur), end: this.fm(cur + step) }); cur += step;
      }
      return out;
    },
  },
  watch: {
    // 营业区间变化时收缩休息/高峰窗口：越界部分裁剪，裁完为空则删除
    "f.open_time"() { this.clampWindows(); },
    "f.close_time"() { this.clampWindows(); },
  },
  async mounted() {
    const seg = this.$route.match;
    // match = ["", "mvenue", "{id}", "edit"]（新建为 ["", "mvenue", "new"]）
    if (seg[3] === "edit" || (seg[3] === undefined && seg[2] !== "new" && Number(seg[2]))) {
      this.isEdit = true;
      const id = parseInt(seg[2], 10);
      const d = await API.fetch(`/api/admin/venues/${id}`);
      this.venueId = id;
      this.f = { name: d.name, address: d.address, phone: d.phone, open_time: d.open_time,
                 close_time: d.close_time, breaks: d.breaks.map(b => ({ ...b })),
                 slot_minutes: d.slot_minutes, peak_start: d.peak_start_time || "", peak_end: d.peak_end_time || "",
                 peak_ratio_bp: d.peak_ratio_bp || 15000, notice: d.notice, court_count: d.court_count,
                 base_price_cents: (d.courts[0] || {}).base_price_cents || 3000 };
      this.courts = d.courts.map(c => ({ ...c, priceYuan: c.base_price_cents / 100 }));
    }
  },
  methods: {
    fm(m) { return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; },
    overlap(a, b) { return this.hm(a.start) < this.hm(b.end) && this.hm(b.start) < this.hm(a.end); },
    optsWindow(from, to, others) {
      // [from, to) 内可选；与 others 任一窗口重叠的选项置灰不可选
      return this.grid.map(v => {
        const t = this.hm(v);
        let disabled = t < from || t >= to;
        if (!disabled) disabled = others.some(w => this.overlap({ start: v, end: this.fm(t + 30) }, w));
        return { v, disabled };
      });
    },
    breakStartOpts(i) {
      const others = this.f.breaks.filter((_, j) => j !== i)
        .concat(this.f.peak_start ? [{ start: this.f.peak_start, end: this.f.peak_end }] : []);
      return this.optsWindow(this.openM, this.closeM, others);
    },
    breakEndOpts(i) {
      const b = this.f.breaks[i] || { start: this.f.open_time };
      const others = this.f.breaks.filter((_, j) => j !== i)
        .concat(this.f.peak_start ? [{ start: this.f.peak_start, end: this.f.peak_end }] : []);
      return this.grid.map(v => {
        const t = this.hm(v);
        let disabled = t <= this.hm(b.start) || t > this.closeM;
        if (!disabled) disabled = others.some(w => this.overlap({ start: b.start, end: v }, w));
        return { v, disabled };
      });
    },
    addBreak() {
      // 默认落在营业区间内第一个不与现有休息/高峰重叠的 30 分钟格
      for (let t = this.openM; t + 30 <= this.closeM; t += 30) {
        const w = { start: this.fm(t), end: this.fm(t + 30) };
        const busy = this.f.breaks.some(b => this.overlap(w, b))
          || (this.f.peak_start && this.overlap(w, { start: this.f.peak_start, end: this.f.peak_end }));
        if (!busy) { this.f.breaks.push(w); return; }
      }
      this.f.breaks.push({ start: this.f.open_time, end: this.fm(this.openM + 30) });
    },
    addPeak() {
      this.f.peak_start = this.fm(Math.max(this.openM, 18 * 60));
      this.f.peak_end = this.fm(Math.min(this.closeM, 22 * 60));
      if (this.hm(this.f.peak_start) >= this.hm(this.f.peak_end)) {
        this.f.peak_start = this.f.open_time;
        this.f.peak_end = this.fm(this.closeM);
      }
      if (!this.f.peak_ratio_bp) this.f.peak_ratio_bp = 15000;
    },
    clampWindows() {
      if (this.openM >= this.closeM) return;
      this.f.breaks = this.f.breaks
        .map(b => {
          const s = Math.max(this.hm(b.start), this.openM), e = Math.min(this.hm(b.end), this.closeM);
          return e - s >= 30 ? { start: this.fm(s), end: this.fm(e) } : null;
        })
        .filter(Boolean);
      if (this.f.peak_start) {
        const s = Math.max(this.hm(this.f.peak_start), this.openM), e = Math.min(this.hm(this.f.peak_end), this.closeM);
        if (e - s >= 30) { this.f.peak_start = this.fm(s); this.f.peak_end = this.fm(e); }
        else { this.f.peak_start = ""; this.f.peak_end = ""; }
      }
    },
    addCourt() {
      const last = this.courts[this.courts.length - 1] || {};
      this.courts.push({ name: `${this.courts.length + 1} 号场`, priceYuan: last.priceYuan || 30, isNew: true });
    },
    async removeCourt(i) {
      const c = this.courts[i];
      if (!(await this.$root.confirm(
        `删除「${c.name}」后，该场地不再出现在之后放场的批次中（已有预约与历史记录保留）。确认删除？`,
        "删除场地", "删除"))) return;
      try {
        await API.fetch(`/api/admin/courts/${c.id}`, { method: "DELETE" });
        c.status = "inactive";
      } catch (e) { this.err = e.message; }
    },
    async submit() {
      this.err = ""; this.ok = "";
      if (!this.f.name) { this.err = "请填写场馆名称"; return; }
      if (this.f.phone && !/^(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8}|400-?\d{3}-?\d{3,4})$/.test(this.f.phone)) {
        this.err = "联系电话格式不正确（支持手机号或座机，如 13800138000 / 0571-88880000）"; return;
      }
      if (this.isEdit) {
        for (const c of this.courts) {
          if (!c.name || !c.priceYuan || c.priceYuan <= 0) { this.err = "场地名称与单价需填写完整"; return; }
        }
      }
      this.busy = true;
      try {
        if (this.isEdit) {
          await API.fetch(`/api/admin/venues/${this.venueId}`, { method: "PATCH",
            body: JSON.stringify({ name: this.f.name, address: this.f.address, phone: this.f.phone,
              open_time: this.f.open_time, close_time: this.f.close_time, breaks: this.f.breaks,
              slot_minutes: this.f.slot_minutes,
              peak_start_time: this.f.peak_start || null, peak_end_time: this.f.peak_end || null,
              peak_ratio_bp: this.f.peak_ratio_bp, notice: this.f.notice })});
          for (const c of this.courts) {
            const price = Math.round((Number(c.priceYuan) || 0) * 100);
            if (c.isNew) {
              await API.fetch("/api/admin/courts", { method: "POST",
                body: JSON.stringify({ venue_id: this.venueId, name: c.name, base_price_cents: price })});
            } else {
              await API.fetch(`/api/admin/courts/${c.id}`, { method: "PATCH",
                body: JSON.stringify({ name: c.name, base_price_cents: price })});
            }
          }
          this.ok = "已保存：配置与价格将对之后放场的批次生效，新场地立即可用于放场";
        } else {
          if (!this.f.court_count || this.priceYuan <= 0) { this.err = "请填写场地数量与单价"; return; }
          const r = await API.fetch("/api/admin/venues", { method: "POST", body: JSON.stringify({
            ...this.f, peak_start_time: this.f.peak_start || null, peak_end_time: this.f.peak_end || null })});
          this.ok = `已创建「${r.name}」（${r.court_count} 块场地），可在列表中放场`;
          setTimeout(() => { location.hash = "#/mvenues"; }, 900);
        }
      } catch (e) { this.err = e.message; }
      finally { this.busy = false; }
    },
  },
};
