window.VIEWS = window.VIEWS || {};
VIEWS.bookings = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="t" style="padding-left:2px"><div class="tt">我的预约</div>
        <div class="ts">共 {{ items.length }} 条记录</div></div>
      <div class="u">{{ $root.nickname || "我的" }}</div>
    </div>
    <div class="seg">
      <button v-for="f in filters" :key="f.v" :class="{ on: filter === f.v }" @click="filter = f.v">{{ f.t }}</button>
    </div>
    <div class="date-row" v-if="dateOptions.length > 1">
      <div class="dchip" v-for="d in dateOptions" :key="d" :class="{ on: dateFilter === d }" @click="dateFilter = d">
        <span class="w">{{ d === "" ? "全部" : "周" + "日一二三四五六"[new Date(d + "T00:00:00").getDay()] }}</span>{{ d.slice(5) || "" }}</div>
    </div>
    <div class="bk-card glass" v-for="b in filtered" :key="b.booking_no">
      <div class="bk-head">
        <div class="bk-title">{{ title(b) }}<div class="bk-no">{{ b.booking_no }}</div></div>
        <span class="tag" :class="statusTag(b.status)">{{ statusText(b.status) }}</span></div>
      <div class="bk-row"><span>日期</span><b>{{ dateLabel(b) }}</b></div>
      <div class="bk-row" v-if="b.status === 'pending_paid'"><span>剩余支付时间</span>
        <span class="tm">${ICONS.clock}{{ remain(b) }}</span></div>
      <div class="bk-row" v-else-if="b.status === 'paid'"><span>支付截止</span><b>{{ shortTime(b.expire_at) }}</b></div>
      <div class="bk-ft">
        <span class="bk-amt" :style="b.status === 'cancelled' ? 'color:#98a49d' : ''">¥{{ (b.total_cents / 100).toFixed(2) }}</span>
        <div class="bk-btns">
          <template v-if="b.status === 'pending_paid'">
            <button class="bk-btn solid" @click="goPay(b)">去支付</button>
            <button class="bk-btn line" @click="cancel(b)">取消预约</button>
          </template>
          <template v-else-if="b.status === 'paid'">
            <button class="bk-btn line" @click="cancel(b)">取消预约</button>
            <button class="bk-btn line" @click="goDetail(b)">查看明细</button>
          </template>
          <template v-else>
            <button class="bk-btn line" @click="goDetail(b)">查看明细</button>
          </template>
        </div></div>
      <div class="muted" style="margin-top:8px" v-if="msg[b.booking_no]">{{ msg[b.booking_no] }}</div>
    </div>
    <div class="empty" v-if="!items.length">${ICONS.list}暂无预约</div>
  </div>`,
  data: () => ({ items: [], filter: "", dateFilter: "", msg: {}, now: Date.now(), timer: null }),
  computed: {
    filters() {
      return [{ v: "", t: "全部" }, { v: "pending_paid", t: "待支付" }, { v: "paid", t: "已支付" },
              { v: "refunded", t: "已退款" }, { v: "cancelled", t: "已取消" }];
    },
    dateOptions() {
      const set = new Set();
      for (const b of this.items) {
        const it = (b.items || [])[0];
        if (it) set.add(it.slot_date);
      }
      return ["", ...[...set].sort()];
    },
    filtered() {
      let out = this.filter ? this.items.filter(b => b.status === this.filter) : this.items;
      if (this.dateFilter) out = out.filter(b => (b.items || [])[0] && b.items[0].slot_date === this.dateFilter);
      return out;
    },
  },
  async mounted() {
    await this.load();
    this.timer = setInterval(() => { this.now = Date.now(); }, 1000);
  },
  beforeUnmount() { clearInterval(this.timer); },
  methods: {
    statusText(s) { return { pending_paid: "待支付", paid: "已预约", refunded: "已退款", cancelled: "已取消", finished: "已完成" }[s] || s; },
    statusTag(s) { return { pending_paid: "pay", paid: "ok", refunded: "sand", cancelled: "cancel", finished: "ok" }[s] || ""; },
    title(b) {
      const it = (b.items || [])[0];
      if (!it) return "预约 " + b.item_count + " 个时段";
      return it.court_name + " · " + it.time_label + (b.item_count > 1 ? ` 等 ${b.item_count} 个时段` : "");
    },
    dateLabel(b) {
      const it = (b.items || [])[0];
      if (!it) return "-";
      return it.slot_date.slice(5);
    },
    shortTime(t) { return (t || "").slice(5, 16).replace("T", " "); },
    remain(b) {
      const sec = Math.max(0, Math.floor((new Date(b.expire_at).getTime() - this.now) / 1000));
      const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
      return (h ? h + ":" : "") + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
    },
    async load() { this.items = (await API.fetch("/api/bookings")).items; },
    goPay(b) { location.hash = "#/pay/" + b.booking_no; },
    goDetail(b) { location.hash = "#/bookingdetail/" + b.booking_no; },
    async cancel(b) {
      const tip = b.status === "paid"
        ? "已支付订单取消将原路退款（开场前 2 小时内不可取消）。确认取消该预约？"
        : "确认取消该预约？时段将立即释放。";
      if (!(await this.$root.confirm(tip, "取消预约", b.status === "paid" ? "取消并退款" : "确认取消"))) return;
      try {
        await API.fetch(`/api/bookings/${b.booking_no}/cancel`, { method: "POST" });
        await this.load();
      } catch (e) { this.msg[b.booking_no] = e.message; }
    },
  },
};
