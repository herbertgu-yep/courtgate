/* 预约查询：按场馆 + 日期筛选，卡片含用户手机号 */
window.VIEWS = window.VIEWS || {};
VIEWS.venuebookings = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">预约查询 · {{ venue ? venue.name : "" }}</div>
        <div class="ts">按日期筛选当日预约</div></div>
    </div>
    <div class="date-row">
      <div class="dchip" v-for="d in dateOptions" :key="d.v" :class="{ on: date === d.v }" @click="date = d.v; load()">
        <span class="w">{{ d.w }}</span>{{ d.v.slice(5) }}</div>
    </div>
    <div class="seg">
      <button v-for="f in filters" :key="f.v" :class="{ on: status === f.v }" @click="status = f.v; load()">{{ f.t }}</button>
    </div>
    <div class="bk-card glass" v-for="b in items" :key="b.booking_no">
      <div class="bk-head">
        <div class="bk-title">{{ b.user_nickname }}
          <div class="bk-no">${ICONS.user} {{ b.user_phone || "未留手机号" }} · {{ b.booking_no }}</div></div>
        <span class="tag" :class="tagCls(b.status)">{{ tagText(b.status) }}</span></div>
      <div class="bk-row"><span>时段</span><b>{{ b.items.map(i => i.court_name + " " + i.time_label).join("、") }}</b></div>
      <div class="bk-row"><span>下单时间</span><b>{{ (b.created_at || "").slice(5, 16).replace("T", " ") }}</b></div>
      <div class="bk-ft">
        <span class="bk-amt" :style="b.status === 'cancelled' || b.status === 'refunded' ? 'color:#98a49d' : ''">
          ¥{{ (b.total_cents / 100).toFixed(2) }}</span></div>
    </div>
    <div class="empty" v-if="!loading && !items.length">${ICONS.list}该条件下暂无预约</div>
  </div>`,
  data: () => ({ venueId: 0, venue: null, date: "", status: "", items: [], loading: true }),
  computed: {
    dateOptions() {
      const out = [];
      const now = new Date();
      const w = ["日", "一", "二", "三", "四", "五", "六"];
      for (let i = 0; i < 14; i++) {
        const d = new Date(now.getTime() + 86400000 * i);
        const v = d.toISOString().slice(0, 10);
        out.push({ v, w: i === 0 ? "今天" : "周" + w[d.getDay()] });
      }
      return out;
    },
    filters() {
      return [{ v: "", t: "全部" }, { v: "pending_paid", t: "待支付" }, { v: "paid", t: "已支付" },
              { v: "refunded", t: "已退款" }, { v: "cancelled", t: "已取消" }];
    },
  },
  async mounted() {
    this.venueId = parseInt(this.$route.match[2], 10);
    this.venue = await API.fetch(`/api/admin/venues/${this.venueId}`);
    this.date = this.dateOptions[0].v;
    await this.load();
  },
  methods: {
    tagText(s) { return { pending_paid: "待支付", paid: "已支付", refunded: "已退款", cancelled: "已取消", finished: "已完成" }[s] || s; },
    tagCls(s) { return { pending_paid: "pay", paid: "ok", refunded: "sand", cancelled: "cancel", finished: "ok" }[s] || ""; },
    async load() {
      this.loading = true;
      try {
        const qs = new URLSearchParams({ date: this.date });
        if (this.status) qs.set("status", this.status);
        this.items = (await API.fetch(`/api/admin/venues/${this.venueId}/bookings?` + qs)).items;
      } finally { this.loading = false; }
    },
  },
};
