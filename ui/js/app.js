/* hash 路由 + 挂载。所有计算属性在定义时写全；视图通过 this.$route.match/query 取参数。 */
(function () {
  const { createApp } = Vue;

  const App = {
    data: () => ({
      route: "login",
      nickname: localStorage.getItem("cg_nickname") || "",
      admin: localStorage.getItem("cg_admin") === "1",
      needPhone: false,
      phoneInput: "",
      phoneErr: "",
      confirmBox: null,
    }),
    computed: {
      authed() {
        return !!API.token;
      },
      tab() {
        return this.route.split("/")[0] || "home";
      },
      view() {
        // 取路由首段匹配：paysuccess 不能用 startsWith("pay/") 判断
        const key = this.route.split("/")[0];
        const seg = this.route.split("/");
        if (key === "mvenue") {
          // 场馆管理子页：#/mvenue/new、#/mvenue/{id}/{edit|release|closure|bookings}
          if (seg[1] === "new") return "v-venueform";
          if (seg[2] === "edit") return "v-venueform";
          if (seg[2] === "release") return "v-venuerelease";
          if (seg[2] === "closure") return "v-venueclosure";
          if (seg[2] === "bookings") return "v-venuebookings";
          return "v-admin";
        }
        const map = {
          "": "v-home",
          home: "v-home",
          login: "v-login",
          register: "v-register",
          bookings: "v-bookings",
          bookingdetail: "v-bookingdetail",
          profile: "v-profile",
          coupons: "v-coupons",
          mcoupons: "v-mcoupons",
          mvenues: "v-admin",
          admin: "v-admin",
          pay: "v-pay",
          paysuccess: "v-paysuccess",
          slots: "v-slots",
          confirm: "v-confirm",
        };
        return map[key] || "v-home";
      },
      // 只有三个主页面显示 TabBar；子页（选时段/确认/详情/收银台/领券/管理）带返回导航
      showTabbar() {
        return this.authed && ["", "home", "bookings", "profile", "mvenues"].includes(this.tab);
      },
    },
    template: `
    <component :is="view"></component>
    <div class="tabbar" v-if="showTabbar">
      <a href="#/" class="tab" :class="{ on: ['', 'home', 'slots', 'confirm'].includes(tab) }">${ICONS.calendar}预约</a>
      <a href="#/bookings" class="tab" :class="{ on: tab === 'bookings' || tab === 'bookingdetail' }">${ICONS.list}我的预约</a>
      <a href="#/profile" class="tab" :class="{ on: ['profile', 'coupons', 'mvenues', 'mvenue'].includes(tab) }">${ICONS.user}我的</a>
    </div>
    <div class="modal-mask" v-if="confirmBox">
      <div class="modal glass">
        <div class="tt">{{ confirmBox.title || "确认操作" }}</div>
        <p class="muted" style="margin:8px 0 4px">{{ confirmBox.text }}</p>
        <div class="bk-btns" style="margin-top:14px">
          <button class="big-cta line" style="margin:0" @click="resolveConfirm(false)">取消</button>
          <button class="big-cta" style="margin:0" @click="resolveConfirm(true)">{{ confirmBox.okText || "确认" }}</button>
        </div>
      </div>
    </div>
    <div class="modal-mask" v-if="needPhone">
      <div class="modal glass">
        <div class="tt">完善联系方式</div>
        <p class="muted" style="margin:8px 0 4px">留下手机号，场馆调整或退款时便于联系您（选填）。</p>
        <input v-model="phoneInput" maxlength="11" inputmode="numeric" placeholder="11 位手机号">
        <div class="err-box" v-if="phoneErr">{{ phoneErr }}</div>
        <button class="big-cta" style="margin-top:12px" @click="savePhone">保存</button>
        <button class="big-cta line" @click="skipPhone">暂不填写</button>
      </div>
    </div>`,
    created() {
      window.addEventListener("hashchange", () => this.resolve());
      this.resolve();
      if (this.authed) this.checkPhone();
    },
    methods: {
      resolve() {
        this.route = (location.hash || "#/").slice(2).split("?")[0] || "home";
        const publicPages = ["login", "register"];
        if (!API.token && !publicPages.includes(this.route)) {
          // 记住来路，登录后跳回
          if (this.route !== "login") {
            sessionStorage.setItem("cg_redirect", "#" + location.hash.slice(1));
            location.hash = "#/login";
          }
          this.route = "login";
          return;
        }
        if (API.token && this.route === "login") this.route = "home";
      },
      async checkPhone() {
        // 首次登录引导补手机号；每次会话只提示一次
        if (sessionStorage.getItem("cg_phone_done")) return;
        try {
          const me = await API.fetch("/api/auth/me");
          if (!me.phone_number) this.needPhone = true;
          else sessionStorage.setItem("cg_phone_done", "1");
        } catch (e) { /* 忽略 */ }
      },
      // 自设计确认弹窗：替代原生 window.confirm，返回 Promise<boolean>
      confirm(text, title, okText) {
        return new Promise((resolve) => {
          this.confirmBox = { text, title, okText, _resolve: resolve };
        });
      },
      resolveConfirm(v) {
        if (this.confirmBox && this.confirmBox._resolve) this.confirmBox._resolve(v);
        this.confirmBox = null;
      },
      async savePhone() {
        this.phoneErr = "";
        if (!/^1[3-9]\d{9}$/.test(this.phoneInput)) { this.phoneErr = "请输入 11 位手机号（1 开头）"; return; }
        try {
          await API.fetch("/api/auth/phone", { method: "POST", body: JSON.stringify({ phone: this.phoneInput }) });
          this.needPhone = false;
          sessionStorage.setItem("cg_phone_done", "1");
        } catch (e) { this.phoneErr = e.message; }
      },
      skipPhone() {
        this.needPhone = false;
        sessionStorage.setItem("cg_phone_done", "1");
      },
      afterAuth(tokens) {
        // tokens: { access_token, refresh_token, nickname, role }
        API.setToken(tokens.access_token);
        if (tokens.nickname) {
          this.nickname = tokens.nickname;
          localStorage.setItem("cg_nickname", tokens.nickname);
        }
        localStorage.setItem("cg_admin", tokens.role === "operator" ? "1" : "0");
        this.admin = tokens.role === "operator";
        const redirect = sessionStorage.getItem("cg_redirect");
        if (redirect) {
          sessionStorage.removeItem("cg_redirect");
          location.hash = redirect;
        } else {
          location.hash = "#/";
        }
        this.checkPhone();
      },
      logout() {
        API.setToken("");
        localStorage.removeItem("cg_nickname");
        localStorage.removeItem("cg_admin");
        sessionStorage.removeItem("cg_phone_done");
        this.nickname = "";
        this.admin = false;
        this.needPhone = false;
        this.resolve();
      },
    },
  };

  const app = createApp(App);
  app.config.globalProperties.$back = () => history.back();
  app.config.globalProperties.$go = (h) => { location.hash = h; };
  app.config.globalProperties.$route = {
    get match() {
      return (location.hash || "").slice(1).split("?")[0].split("/");
    },
    get query() {
      const qs = (location.hash || "").split("?")[1] || "";
      return Object.fromEntries(new URLSearchParams(qs));
    },
  };
  app.component("v-home", VIEWS.home);
  app.component("v-slots", VIEWS.slots);
  app.component("v-confirm", VIEWS.confirm);
  app.component("v-bookings", VIEWS.bookings);
  app.component("v-bookingdetail", VIEWS.bookingdetail);
  app.component("v-profile", VIEWS.profile);
  app.component("v-coupons", VIEWS.coupons);
  app.component("v-login", VIEWS.login);
  app.component("v-register", VIEWS.register);
  app.component("v-pay", VIEWS.pay);
  app.component("v-paysuccess", VIEWS.paysuccess);
  app.component("v-admin", VIEWS.admin);
  app.component("v-mcoupons", VIEWS.mcoupons);
  app.component("v-venueform", VIEWS.venueform);
  app.component("v-venuerelease", VIEWS.venuerelease);
  app.component("v-venueclosure", VIEWS.venueclosure);
  app.component("v-venuebookings", VIEWS.venuebookings);
  app.mount("#app");
})();
