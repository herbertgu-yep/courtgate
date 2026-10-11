window.VIEWS = window.VIEWS || {};
VIEWS.pay = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">收银台</div><div class="ts">{{ bookingNo }}</div></div>
    </div>
    <div class="pay-amount glass" style="margin:12px 14px 0">
      <div class="lab">应付金额</div>
      <div class="amt">¥{{ (amount / 100).toFixed(2) }}</div>
      <span class="cd" v-if="remainSec > 0">${ICONS.clock}支付剩余 {{ Math.floor(remainSec / 60) }}:{{ String(remainSec % 60).padStart(2, "0") }}</span>
      <span class="tag pay" v-else>支付已超时，时段已释放</span>
    </div>
    <div class="sec-card glass">
      <div class="sec-t">选择支付方式</div>
      <div class="ch-row" v-for="c in channels" :key="c.code" :class="{ on: channel === c.code }" @click="channel = c.code">
        <span class="l">${ICONS.card}{{ c.label }}
          <span class="tag sand" v-if="c.sandbox">沙箱</span></span>
        <span class="radio-dot"></span></div>
    </div>
    <div class="err-box" v-if="err" style="margin:12px 14px">{{ err }}</div>
    <button class="big-cta" @click="confirmPay" :disabled="busy || remainSec <= 0">
      {{ busy ? "支付处理中…" : "立即支付" }}</button>
    <button class="big-cta line" @click="back">暂不支付，稍后支付</button>
  </div>`,
  data: () => ({ bookingNo: "", amount: 0, channels: [], channel: "",
                remainSec: 0, busy: false, err: "", timer: null }),
  async mounted() {
    this.bookingNo = this.$route.match[2];
    const b = await API.fetch(`/api/bookings/${this.bookingNo}`);
    this.amount = b.total_cents;
    this.channels = (await API.fetch("/api/payments/channels")).items;
    this.channel = (this.channels[0] || {}).code || "";
    this.tickRemain(b.expire_at);
  },
  beforeUnmount() { clearInterval(this.timer); },
  methods: {
    tickRemain(expireAt) {
      const tick = () => {
        const sec = Math.floor((new Date(expireAt).getTime() - Date.now()) / 1000);
        this.remainSec = Math.max(0, sec);
        if (this.remainSec <= 0) clearInterval(this.timer);
      };
      tick();
      this.timer = setInterval(tick, 1000);
    },
    back() { location.hash = "#/bookings"; },
    async confirmPay() {
      this.busy = true; this.err = "";
      try {
        const p = await API.fetch(`/api/payments/${this.bookingNo}`, {
          method: "POST", body: JSON.stringify({ channel: this.channel })});
        const ch = this.channels.find(c => c.code === this.channel);
        if (ch && ch.sandbox) {
          // 沙箱渠道：本地代第三方发起回调（签名合法，等同真实回调）
          const cbBody = await API.fetch("/api/payments/mock_callback_body", {
            method: "POST",
            body: JSON.stringify({ payment_no: p.payment_no, channel: this.channel,
                                   amount_cents: p.amount_cents })});
          await API.fetch(`/api/payments/callback/${this.channel}`, {
            method: "POST", body: JSON.stringify(cbBody)});
          sessionStorage.setItem("cg_paid_amount", String(p.amount_cents));
          location.hash = "#/paysuccess/" + this.bookingNo;
        } else {
          // 真实渠道：跳转第三方支付页，回调由第三方服务器发起
          if (p.pay_url) { window.location.href = p.pay_url; return; }
          location.hash = "#/bookings";
        }
      } catch (e) { this.err = e.message; this.busy = false; }
    },
  },
};
