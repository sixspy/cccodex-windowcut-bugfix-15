import { createApi } from "./api.js";
import { windowsViewTemplate } from "./views/windows_view.js";
import { ingestViewTemplate } from "./views/ingest_view.js";
import { lateViewTemplate } from "./views/late_view.js";
import { materializeViewTemplate } from "./views/materialize_view.js";
import { reconcileViewTemplate } from "./views/reconcile_view.js";
import { auditViewTemplate } from "./views/audit_view.js";

const { createApp, ref, onMounted, computed } = Vue;

createApp({
  setup() {
    const token = ref(localStorage.getItem("windowcut_token") || "");
    const user = ref(localStorage.getItem("windowcut_user") || "");
    const username = ref("admin");
    const password = ref("123456");
    const err = ref("");
    const tab = ref(0);
    const actionErr = ref("");
    const windows = ref([]);
    const events = ref([]);
    const mats = ref([]);
    const recon = ref({});
    const reconAll = ref([]);
    const lateItems = ref([]);
    const lateSummary = ref({});
    const audits = ref([]);
    const contention = ref([]);
    const locks = ref([]);
    const holds = ref([]);
    const dash = ref({});
    const form = ref({
      window_name: "W-1102",
      biz_key: "ORD-9",
      event_ts: "2026-11-02T12:00:00",
      amount: 8.8,
    });
    const holdForm = ref({
      window_name: "W-1102",
      biz_key: "HOLD-1",
      event_ts: "2026-11-02T18:00:00",
      amount: 2.2,
    });
    const nav = ["业务窗", "事件入账", "迟到桶", "物化台账", "对账互证", "审计争用"];

    function logout() {
      token.value = "";
      user.value = "";
      localStorage.removeItem("windowcut_token");
      localStorage.removeItem("windowcut_user");
    }

    const api = createApi(
      () => token.value,
      () => logout()
    );

    async function login() {
      err.value = "";
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.value,
          password: password.value,
        }),
      });
      const j = await r.json();
      if (!r.ok) {
        err.value = j.detail || "登录失败";
        return;
      }
      token.value = j.token;
      user.value = j.username;
      localStorage.setItem("windowcut_token", j.token);
      localStorage.setItem("windowcut_user", j.username);
      await refresh();
    }

    async function refresh() {
      if (!token.value) return;
      const w = await api.get("/api/windows");
      if (w === null) return;
      windows.value = Array.isArray(w.body.items) ? w.body.items : [];
      const e = await api.get("/api/events");
      if (e === null) return;
      events.value = Array.isArray(e.body.items) ? e.body.items : [];
      const m = await api.get("/api/materializations");
      if (m === null) return;
      mats.value = Array.isArray(m.body.items) ? m.body.items : [];
      const late = await api.get("/api/late-bucket");
      if (late === null) return;
      lateItems.value = Array.isArray(late.body.items) ? late.body.items : [];
      const ls = await api.get("/api/late-bucket/summary");
      if (ls === null) return;
      lateSummary.value = ls.body || {};
      const ra = await api.get("/api/reconcile");
      if (ra === null) return;
      reconAll.value = Array.isArray(ra.body.items) ? ra.body.items : [];
      const au = await api.get("/api/audit?limit=50");
      if (au === null) return;
      audits.value = Array.isArray(au.body.items) ? au.body.items : [];
      const ct = await api.get("/api/contention");
      if (ct === null) return;
      contention.value = Array.isArray(ct.body.items) ? ct.body.items : [];
      const lk = await api.get("/api/locks");
      if (lk === null) return;
      locks.value = Array.isArray(lk.body.items) ? lk.body.items : [];
      const hd = await api.get("/api/holds");
      if (hd === null) return;
      holds.value = Array.isArray(hd.body.items) ? hd.body.items : [];
      const d = await api.get("/api/dashboard");
      if (d === null) return;
      dash.value = d.body || {};
      if (windows.value.length) {
        const q = await api.get("/api/reconcile/" + windows.value[0].id);
        if (q === null) return;
        recon.value = q.body && typeof q.body === "object" ? q.body : {};
      }
    }

    async function ingest() {
      actionErr.value = "";
      const r = await api.post("/api/events", form.value);
      if (!r) return;
      actionErr.value = r.ok
        ? "处置：" + r.body.disposition
        : r.body.detail || "失败";
      await refresh();
    }

    async function closeWin(id) {
      actionErr.value = "";
      const r = await api.post("/api/windows/" + id + "/close", {});
      if (r && !r.ok) actionErr.value = r.body.detail || "关窗失败";
      await refresh();
    }

    async function materialize(id) {
      actionErr.value = "";
      const r = await api.post("/api/windows/" + id + "/materialize", {});
      if (r && !r.ok) actionErr.value = r.body.detail || "失败";
      await refresh();
    }

    async function loadRecon(id) {
      const q = await api.get("/api/reconcile/" + id);
      if (q) recon.value = q.body || {};
    }

    async function reopenStub(id) {
      actionErr.value = "";
      const r = await api.post("/api/windows/" + id + "/reopen-stub", {
        mode: "作废重算",
      });
      if (r && !r.ok) actionErr.value = r.body.detail || "重开空桩失败";
      else if (r) actionErr.value = "重开空桩已登记";
      await refresh();
    }

    async function promoteLate(id) {
      const target =
        (windows.value.find((w) => w.status === "开启") || {}).name || "W-1102";
      await api.post("/api/late-bucket/promote-stub", {
        late_id: id,
        target_window_name: target,
      });
      await refresh();
    }

    async function discardLate(id) {
      await api.post("/api/late-bucket/" + id + "/discard-stub", {});
      await refresh();
    }

    async function partitionStub() {
      await api.post("/api/materializations/partition-stub", {});
      await refresh();
    }

    async function createHold() {
      actionErr.value = "";
      const r = await api.post("/api/holds", holdForm.value);
      if (r && !r.ok) actionErr.value = r.body.detail || "暂存失败";
      await refresh();
    }

    onMounted(() => {
      if (token.value) refresh();
    });

    return {
      token,
      user,
      username,
      password,
      err,
      tab,
      nav,
      windows,
      events,
      mats,
      recon,
      reconAll,
      lateItems,
      lateSummary,
      audits,
      contention,
      locks,
      holds,
      dash,
      form,
      holdForm,
      actionErr,
      lateEvents: computed(() =>
        (events.value || []).filter((e) => e.disposition === "迟到桶")
      ),
      login,
      logout,
      ingest,
      closeWin,
      materialize,
      loadRecon,
      reopenStub,
      promoteLate,
      discardLate,
      partitionStub,
      createHold,
      refresh,
    };
  },
  template: `
  <div v-if="!token" class="login">
    <h1 style="margin:0 0 8px">业务窗关账</h1>
    <p style="color:#6b5f7a">事件按窗裁切；关窗后物化；迟到进旁路桶。加厚母仓含锁/审计/空桩。</p>
    <label>用户名</label><input v-model="username"/>
    <label>密码</label><input type="password" v-model="password"/>
    <div class="err">{{err}}</div>
    <button class="primary" style="width:100%" @click="login">进入关账页</button>
  </div>
  <div v-if="token" class="page">
    <div class="hero">
      <div class="hero-main">
        <h1>业务窗关账</h1>
        <p>把事件落到正确业务窗。窗外且仍开启则拒收；已关闭则进迟到桶。关窗后才能物化，并对齐窗内合计。</p>
        <div class="chips">
          <button class="chip" v-for="(n,i) in nav" :key="n" :class="{on:tab===i}" @click="tab=i">{{n}}</button>
        </div>
      </div>
      <div class="hero-side">
        <div>迟到桶</div>
        <div class="n">{{lateSummary.count||lateEvents.length}}</div>
        <div style="opacity:.8;margin-top:8px">对账对齐：{{recon.aligned}}</div>
        <div style="opacity:.8">争用 {{dash.contention||0}} · 暂存 {{dash.holds||0}}</div>
        <div style="margin-top:16px;font-size:12px;opacity:.75">{{user}} · <a href="#" style="color:#fff" @click.prevent="logout">退出</a></div>
      </div>
    </div>
    <div class="stat-row">
      <div class="stat"><div class="k">开启窗</div><div class="v">{{dash.open_windows||0}}</div></div>
      <div class="stat"><div class="k">已关窗</div><div class="v">{{dash.closed_windows||0}}</div></div>
      <div class="stat"><div class="k">拒收</div><div class="v">{{dash.rejects||0}}</div></div>
      <div class="stat"><div class="k">物化单</div><div class="v">{{dash.materializations||0}}</div></div>
    </div>
    <div class="board">
      ${windowsViewTemplate}
      ${ingestViewTemplate}
      ${lateViewTemplate}
      ${materializeViewTemplate}
      ${reconcileViewTemplate}
      ${auditViewTemplate}
    </div>
    <div class="foot">
      <span>业务窗关账 · 本地 SQLite · docker compose 一键起</span>
      <span>关窗后物化，迟到不进本窗合计 · 多模块空桩待挖题</span>
    </div>
  </div>
  `,
}).mount("#app");
