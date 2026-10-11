/* fetch 封装：token 自动携带、401 跳登录、统一解包错误体。价格一律后端算。 */
window.API = {
  base: "",
  token: localStorage.getItem("cg_token") || "",

  setToken(t) {
    this.token = t || "";
    if (t) localStorage.setItem("cg_token", t); else localStorage.removeItem("cg_token");
  },

  async fetch(path, opts = {}) {
    const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    if (this.token) headers.Authorization = "Bearer " + this.token;
    const r = await fetch(this.base + path, { ...opts, headers });
    if (r.status === 401 && !path.startsWith("/api/auth")) {
      this.setToken("");
      sessionStorage.setItem("cg_redirect", location.hash || "#/");
      location.hash = "#/login";
      throw new Error("请先登录");
    }
    const body = await r.json();
    if (!r.ok) {
      const msg = (body.error && body.error.message) || "请求失败";
      const err = new Error(msg);
      err.code = body.error && body.error.code;
      err.details = body.error && body.error.details;
      err.status = r.status;
      throw err;
    }
    return body;
  },
};
