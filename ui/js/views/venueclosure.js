/* 休息日设置：预览受影响预约 → 确认后自动取消/退款并通知 */
window.VIEWS = window.VIEWS || {};
VIEWS.venueclosure = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">休息日 · {{ venue ? venue.name : "" }}</div>
        <div class="ts">有预约时先预览，确认后自动取消/退款并通知用户</div></div>
    </div>
    <div class="form-card glass">
      <label class="fl">休息日期</label>
      <input v-model="date" type="date">
      <button class="big-cta" @click="preview" :disabled="!date" style="margin-top:12px">查询该日受影响的预约</button>
    </div>
    <div class="sec-card glass" v-if="pv">
      <div class="sec-t">受影响预约<span>{{ pv.count }} 笔</span></div>
      <div class="sec-row" v-for="b in pv.bookings" :key="b.booking_no">
        <div><div class="tt">{{ b.user_nickname }}
            <span class="muted">{{ b.user_phone || "未留手机号" }}</span></div>
          <div class="sub">{{ b.time_labels }} · ¥{{ (b.total_cents / 100).toFixed(2) }} ·
            {{ { pending_paid: "待支付", paid: "已支付" }[b.status] || b.status }}</div></div>
        <span class="tag" :class="b.status === 'paid' ? 'ok' : 'pay'">{{ b.status === "paid" ? "将退款" : "将取消" }}</span>
      </div>
      <div class="empty" v-if="!pv.count">${ICONS.check}该日期没有预约，可直接设置休息</div>
    </div>
    <div class="form-card glass" v-if="pv && pv.count">
      <label class="fl">通知内容（选填，留空发送默认文案）</label>
      <textarea v-model="msg" rows="3" maxlength="300"
        style="width:100%;border:1px solid rgba(255,255,255,.9);border-radius:12px;padding:11px 13px;font-size:13px;background:rgba(255,255,255,.6);font-family:inherit"
        placeholder="如：因设备检修暂停营业一天，给您带来不便敬请谅解，预约将全额退款"></textarea>
    </div>
    <div class="err-box" v-if="err" style="margin:12px 14px">{{ err }}</div>
    <div class="ok-box" v-if="result" style="margin:12px 14px">
      ${ICONS.check} 已设置 {{ result.closure_date }} 休息：取消 {{ result.cancelled }} 笔，退款 {{ result.refunded }} 笔，站内信已送达
    </div>
    <button class="big-cta" v-if="pv" @click="confirm" :disabled="busy" style="width:calc(100% - 28px)">
      {{ busy ? "处理中…" : pv.count ? "确认闭馆：取消/退款并通知" : "确认设置休息" }}</button>
  </div>`,
  data: () => ({ venueId: 0, venue: null, date: "", pv: null, msg: "", err: "", result: null, busy: false }),
  async mounted() {
    this.venueId = parseInt(this.$route.match[2], 10);
    const d = await API.fetch(`/api/admin/venues/${this.venueId}`);
    this.venue = d;
  },
  methods: {
    async preview() {
      this.err = ""; this.result = null;
      try {
        this.pv = await API.fetch(`/api/admin/venues/${this.venueId}/closures/preview`, {
          method: "POST", body: JSON.stringify({ closure_date: this.date })});
      } catch (e) { this.err = e.message; }
    },
    async confirm() {
      const tip = this.pv.count
        ? `该日有 ${this.pv.count} 笔预约：待支付将自动取消，已支付将原路退款，并向用户发送通知。确认继续？`
        : `确认将 ${this.date} 设为休息日？`;
      if (!(await this.$root.confirm(tip, "设置休息日", "确认处理"))) return;
      this.busy = true; this.err = "";
      try {
        this.result = await API.fetch(`/api/admin/venues/${this.venueId}/closures`, {
          method: "POST", body: JSON.stringify({ closure_date: this.date,
                                                 notify_content: this.msg || null, force: true })});
        this.pv = null;
      } catch (e) { this.err = e.message; }
      finally { this.busy = false; }
    },
  },
};
