window.VIEWS = window.VIEWS || {};
VIEWS.paysuccess = {
  template: `
  <div class="page paysuccess">
    <div class="check-ring">${ICONS.check}</div>
    <div class="tt">支付成功</div>
    <div class="amt">¥{{ (amount / 100).toFixed(2) }}</div>
    <div class="sum-card glass" style="text-align:left;margin-top:20px">
      <div class="kv"><span>预约单号</span><b>{{ bookingNo }}</b></div>
      <div class="kv"><span>积分到账</span><b style="color:var(--pri-d)">+{{ pointsEarned }}</b></div>
    </div>
    <button class="big-cta" @click="goBookings" style="margin-top:20px">查看我的预约</button>
    <button class="big-cta line" @click="goHome">返回首页</button>
  </div>`,
  data: () => ({ bookingNo: "", amount: 0, pointsEarned: 0 }),
  async mounted() {
    this.bookingNo = this.$route.match[2];
    try {
      const headers = { Authorization: "Bearer " + API.token };
      const b = await API.fetch(`/api/bookings/${this.bookingNo}`, { headers });
      this.amount = b.total_cents;
      const ledger = await API.fetch("/api/points/ledger", { headers });
      const earn = ledger.items.find(l => l.ref_booking_no === this.bookingNo && l.change_type === "earn");
      this.pointsEarned = earn ? earn.points : 0;
    } catch (e) { /* 忽略 */ }
  },
  methods: {
    goBookings() { location.hash = "#/bookings"; },
    goHome() { location.hash = "#/"; },
  },
};
