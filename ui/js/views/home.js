window.VIEWS = window.VIEWS || {};
VIEWS.home = {
  template: `
  <div class="page">
    <div class="home-top">
      <div class="logo">Court<span>Gate</span></div>
      <a class="user" href="#/profile" style="text-decoration:none"><i></i>{{ $root.nickname || "我的" }}</a>
    </div>
    <div class="date-row" v-if="venues.length > 1">
      <div class="dchip" v-for="v in venues" :key="v.id" :class="{ on: v.id === venueId }"
           style="width:auto;padding:9px 14px" @click="switchVenue(v.id)">{{ v.name }}</div>
    </div>
    <div class="venue-card glass" v-if="venue">
      <div class="v-tag">综合场馆</div>
      <div class="v-name">{{ venue.name }}</div>
      <div class="v-meta">${ICONS.pin}{{ venue.address }} · 营业 {{ venue.open_time.slice(0,5) }} – {{ venue.close_time.slice(0,5) }}</div>
      <div class="v-rules">
        <span class="v-rule">${ICONS.clock}预约后 15 分钟内支付</span>
        <span class="v-rule">${ICONS.shield}开场前 2 小时免费取消</span>
      </div>
    </div>
    <div class="act-card glass" v-for="r in releases" :key="r.id">
      <div class="act-head"><div class="act-name">{{ r.name }}</div>
        <span class="badge" :class="{ gray: r.status !== 'open' }">
          {{ r.status === "open" ? "抢约中" : r.status === "pending" ? "未开抢" : "已结束" }}</span></div>
      <div class="act-row"><span>场次周期</span><b>{{ r.period_start.slice(5) }} ~ {{ r.period_end.slice(5) }}</b></div>
      <div class="act-row"><span>每人限约</span><b>{{ r.per_user_limit }} 个时段</b></div>
      <button class="cta" @click="enter(r)" :disabled="r.status !== 'open' && r.status !== 'pending'">
        {{ r.status === "open" ? "进入选时段" : r.status === "pending" ? "查看" : "已结束" }} ${ICONS.arrowR}</button>
    </div>
    <div class="empty" v-if="!loading && !releases.length">${ICONS.calendar}该场馆暂无放场批次</div>
    <div class="tip">${ICONS.info}支持积分抵扣与优惠券，可在「我的」页领取</div>
  </div>`,
  data: () => ({ venues: [], venueId: 0, releases: [], loading: true }),
  computed: {
    venue() {
      return this.venues.find(v => v.id === this.venueId) || null;
    },
  },
  async mounted() {
    try {
      const vs = await API.fetch("/api/venues");
      this.venues = vs.items;
      // 记住上次选择的场馆；默认第一个
      const saved = parseInt(localStorage.getItem("cg_venue_id"), 10);
      this.venueId = this.venues.some(v => v.id === saved) ? saved : (this.venues[0] || {}).id || 0;
      await this.loadReleases();
    } finally { this.loading = false; }
  },
  methods: {
    async switchVenue(id) {
      if (id === this.venueId) return;
      this.venueId = id;
      localStorage.setItem("cg_venue_id", String(id));
      this.loading = true;
      try { await this.loadReleases(); } finally { this.loading = false; }
    },
    async loadReleases() {
      this.releases = this.venueId
        ? (await API.fetch("/api/releases?venue_id=" + this.venueId)).items
        : [];
    },
    enter(r) { location.hash = "#/slots/" + r.id + "?vn=" + encodeURIComponent(this.venue ? this.venue.name : ""); },
  },
};
