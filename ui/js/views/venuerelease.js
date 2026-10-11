/* 放场：为指定场馆按营业日期批量生成预约表；已有批次可按当前配置重生成 */
window.VIEWS = window.VIEWS || {};
VIEWS.venuerelease = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">放场 · {{ venue ? venue.name : "" }}</div>
        <div class="ts">时段价格在放场时固化；改配置后新放或重生成才会生效</div></div>
    </div>
    <div class="form-card glass" v-if="venue">
      <div class="muted" style="margin-bottom:8px">${ICONS.clock}
        营业 {{ venue.open_time }}–{{ venue.close_time }} · {{ venue.slot_minutes }} 分钟/段 ·
        {{ venue.court_count }} 块场地
        <span v-if="venue.breaks.length"> · 休息：{{ venue.breaks.map(b => b.start + "–" + b.end).join("、") }}</span>
        · {{ peakText }}</div>
      <label class="fl">批次名称</label>
      <input v-model="f.name" maxlength="50" placeholder="如：第 2 周周末场">
      <label class="fl">营业日期（起始 / 终止）</label>
      <div class="cap-row">
        <input v-model="f.period_start" type="date">
        <input v-model="f.period_end" type="date">
      </div>
      <label class="fl">开抢时刻</label>
      <input v-model="f.open_at" type="datetime-local">
      <label class="fl">停止预约时刻</label>
      <input v-model="f.close_at" type="datetime-local">
      <label class="fl">每人限约（时段数）</label>
      <input v-model.number="f.per_user_limit" type="number" min="1" max="20">
      <div class="err-box" v-if="err">{{ err }}</div>
      <div class="ok-box" v-if="result">
        ${ICONS.check} 已生成 {{ result.generated }} 个可约时段（批次 #{{ result.release_id }}），
        前端「预约」页即可选购
      </div>
      <button class="big-cta" @click="submit" :disabled="busy" style="margin-top:14px">
        {{ busy ? "生成中…" : "点击放场，生成预约表" }}</button>
    </div>
    <div class="sec-card glass" v-if="venue">
      <div class="sec-t">已有批次<span>价格固化，改配置后可按当前配置重生成</span></div>
      <div class="sec-row" v-for="r in releases" :key="r.id">
        <div style="flex:1">
          <div class="tt">#{{ r.id }} {{ r.name }}
            <span class="tag" :class="r.status === 'open' ? 'ok' : r.status === 'pending' ? 'pay' : 'cancel'">
              {{ r.status === "open" ? "抢约中" : r.status === "pending" ? "未开抢" : "已结束" }}</span></div>
          <div class="sub">{{ r.period_start.slice(5) }} ~ {{ r.period_end.slice(5) }} · 每人限约 {{ r.per_user_limit }}</div>
        </div>
        <button class="bk-btn line" @click="regen(r)" :disabled="busy">重生成时段</button>
      </div>
      <div class="empty" v-if="!releases.length">${ICONS.calendar}还没有批次，用上方表单放第一场</div>
    </div>
  </div>`,
  data: () => ({ venueId: 0, venue: null, releases: [],
                f: { name: "", period_start: "", period_end: "", open_at: "", close_at: "", per_user_limit: 3 },
                err: "", result: null, busy: false }),
  computed: {
    peakText() {
      if (!this.venue || !this.venue.peak_start_time) return "无高峰，统一价";
      return "高峰 " + this.venue.peak_start_time + "–" + this.venue.peak_end_time + " ×" + this.peakMult;
    },
    peakMult() {
      const bp = Number(this.venue && this.venue.peak_ratio_bp) || 15000;
      return String(bp / 10000).replace(/0+$/, "").replace(/\.$/, "") || "1";
    },
  },
  async mounted() {
    this.venueId = parseInt(this.$route.match[2], 10);
    const d = await API.fetch(`/api/admin/venues/${this.venueId}`);
    this.venue = d;
    await this.loadReleases();
    const now = new Date();
    const iso = x => new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    const start = new Date(now.getTime() + 86400000);
    const end = new Date(now.getTime() + 7 * 86400000);
    this.f = { name: "放场 " + now.toLocaleDateString(), period_start: start.toISOString().slice(0, 10),
               period_end: end.toISOString().slice(0, 10), open_at: iso(now),
               close_at: iso(new Date(now.getTime() + 30 * 86400000)), per_user_limit: 3 };
  },
  methods: {
    async loadReleases() {
      this.releases = (await API.fetch("/api/releases?venue_id=" + this.venueId)).items;
    },
    async regen(r) {
      if (!(await this.$root.confirm(`将按场馆当前配置重生成批次 #${r.id} 的时段与价格，仅在该批次从未产生预约时允许。`, "重生成时段", "重生成"))) return;
      this.busy = true; this.err = ""; this.result = null;
      try {
        this.result = await API.fetch(`/api/admin/releases/${r.id}/regenerate`, { method: "POST" });
        await this.loadReleases();
      } catch (e) { this.err = e.message; }
      finally { this.busy = false; }
    },
    async submit() {
      this.err = ""; this.result = null;
      if (!this.f.period_start || !this.f.period_end || !this.f.open_at || !this.f.close_at) {
        this.err = "请完整填写日期与时刻"; return;
      }
      this.busy = true;
      try {
        const iso = d => new Date(d).toISOString().slice(0, 19);
        this.result = await API.fetch("/api/admin/releases", { method: "POST", body: JSON.stringify({
          ...this.f, venue_id: this.venueId,
          open_at: iso(new Date(this.f.open_at)), close_at: iso(new Date(this.f.close_at)) })});
        await this.loadReleases();
      } catch (e) { this.err = e.message; }
      finally { this.busy = false; }
    },
  },
};
