window.VIEWS = window.VIEWS || {};
VIEWS.slots = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">选择时段</div>
        <div class="ts">{{ this.$route.query.vn ? this.$route.query.vn + " · " : "" }}已选 {{ picked.length }} / {{ perUserLimit }} 个时段</div></div>
      <div class="u">{{ $root.nickname || "未登录" }}</div>
    </div>
    <div class="date-row">
      <div v-for="d in dates" :key="d" class="dchip" :class="{ on: d === date }" @click="pickDate(d)">
        <span class="w">{{ closedDates.includes(d) ? "休息" : weekLabel(d) }}</span>{{ d.slice(5) }}</div>
    </div>
    <div class="err-box" style="margin:12px 14px 0" v-if="isClosed">
      ${ICONS.info} 该日场馆休息，不可预约；请选择其它日期
    </div>
    <div class="limit"><span>每人限约 {{ perUserLimit }} 个时段</span><span>已选 <b>{{ picked.length }}</b> / {{ perUserLimit }}</span></div>
    <div class="court glass" v-for="c in courts" :key="c.court_id">
      <div class="court-h"><div class="court-n">{{ c.court_name }}</div>
        <div class="court-p">{{ yuan(c.slots) }}</div></div>
      <div class="grid">
        <div v-for="s in c.slots" :key="s.court_slot_id" class="slot" :class="cls(c, s)" @click="toggle(s)"
             :style="isClosed ? 'pointer-events:none' : ''">
          {{ s.label.slice(0, 5) }}<div class="p">{{ s.available ? "¥" + (s.price_cents / 100).toFixed(0) : "已约" }}</div>
        </div>
      </div>
    </div>
    <div class="empty" v-if="!courts.length">${ICONS.calendar}该日期暂无时段</div>
    <div class="legend">
      <span><i style="background:#12b76a"></i>可预约</span>
      <span v-if="hasPeak"><i style="background:#ffb400"></i>高峰价</span>
      <span><i style="background:#c4ccc7"></i>已约</span>
    </div>
    <div class="bar">
      <div class="n">已选 <b>{{ picked.length }}</b> 个时段 · 合计 ¥{{ (sumCents / 100).toFixed(0) }}</div>
      <button class="go" @click="goConfirm" :disabled="!picked.length">去预约 ${ICONS.arrowR}</button>
    </div>
  </div>`,
  data: () => ({ releaseId: 0, dates: [], date: "", courts: [], perUserLimit: 3, picked: [],
                 closedDates: [], isClosed: false }),
  computed: {
    hasPeak() {
      for (const c of this.courts) {
        const prices = new Set(c.slots.filter(x => x.available).map(x => x.price_cents));
        if (prices.size > 1) return true;
      }
      return false;
    },
    sumCents() {
      let sum = 0;
      for (const c of this.courts) {
        for (const s of c.slots) {
          if (this.picked.includes(s.court_slot_id)) sum += s.price_cents;
        }
      }
      return sum;
    },
  },
  async mounted() {
    this.releaseId = parseInt(this.$route.match[2], 10);
    // 日期列表来自可约时段视图本身（无 date 参数 = 全量骨架）
    const full = await API.fetch("/api/releases/" + this.releaseId + "/slots");
    this.dates = full.dates; this.date = full.dates[0];
    this.perUserLimit = full.per_user_limit;
    this.closedDates = full.closed_dates || [];
    this.isClosed = this.closedDates.includes(this.date);
    await this.refresh();
  },
  methods: {
    weekLabel(d) {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const dt = new Date(d + "T00:00:00");
      if (dt.getTime() === today.getTime()) return "今天";
      return "周" + "日一二三四五六"[dt.getDay()];
    },
    yuan(slots) {
      const p = [...new Set(slots.map(s => s.price_cents))];
      return p.length > 1 ? "¥" + Math.min(...p) / 100 + " / 高峰 ¥" + Math.max(...p) / 100
                          : "¥" + (p[0] / 100).toFixed(0);
    },
    cls(court, s) {
      if (this.picked.includes(s.court_slot_id)) return "sel";
      if (!s.available) return "off";
      const prices = court.slots.filter(x => x.available).map(x => x.price_cents);
      return prices.length > 1 && s.price_cents === Math.max(...prices) ? "peak" : "free";
    },
    async pickDate(d) { this.date = d; await this.refresh(); },
    async refresh() {
      const d = await API.fetch(`/api/releases/${this.releaseId}/slots?date=${this.date}`);
      this.courts = d.courts; this.perUserLimit = d.per_user_limit;
      this.isClosed = !!d.closed;
      this.picked = this.picked.filter(id =>
        d.courts.some(c => c.slots.some(s => s.court_slot_id === id && s.available)));
    },
    toggle(s) {
      if (!s.available) return;
      const i = this.picked.indexOf(s.court_slot_id);
      if (i >= 0) this.picked.splice(i, 1);
      else if (this.picked.length < this.perUserLimit) this.picked.push(s.court_slot_id);
    },
    goConfirm() {
      location.hash = `#/confirm/${this.releaseId}?slots=${this.picked.join(",")}`;
    },
  },
};
