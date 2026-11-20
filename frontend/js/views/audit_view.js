export const auditViewTemplate = `
<div class="card" v-show="tab===5">
  <h2>审计流水</h2>
  <table>
    <thead><tr><th>时间</th><th>人</th><th>动作</th><th>目标</th></tr></thead>
    <tbody>
      <tr v-for="a in audits.slice(0,20)" :key="a.id">
        <td>{{a.created_at}}</td>
        <td>{{a.actor}}</td>
        <td>{{a.action}}</td>
        <td>{{a.target}}</td>
      </tr>
    </tbody>
  </table>
</div>
<div class="card" v-show="tab===5">
  <h2>争用 / 锁</h2>
  <p class="muted">争用 {{contention.length}} · 持锁 {{locks.length}}</p>
  <table>
    <thead><tr><th>锁键</th><th>角色</th><th>动作</th><th>时间</th></tr></thead>
    <tbody>
      <tr v-for="c in contention.slice(0,15)" :key="'c'+c.id">
        <td>{{c.lock_key}}</td>
        <td>{{c.actor}}</td>
        <td>{{c.action}}</td>
        <td>{{c.created_at}}</td>
      </tr>
    </tbody>
  </table>
  <h2 style="margin-top:16px">旁路暂存</h2>
  <label>窗口</label><input v-model="holdForm.window_name"/>
  <label>业务键</label><input v-model="holdForm.biz_key"/>
  <label>时间</label><input v-model="holdForm.event_ts"/>
  <label>金额</label><input type="number" v-model.number="holdForm.amount"/>
  <button class="primary" @click="createHold">写入暂存</button>
  <table>
    <thead><tr><th>ID</th><th>键</th><th>金额</th><th>状态</th></tr></thead>
    <tbody>
      <tr v-for="h in holds" :key="'h'+h.id">
        <td>{{h.id}}</td><td>{{h.biz_key}}</td><td>{{h.amount}}</td><td>{{h.status}}</td>
      </tr>
    </tbody>
  </table>
</div>
`;
