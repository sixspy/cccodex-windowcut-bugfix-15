export const lateViewTemplate = `
<div class="card wide" v-show="tab===2">
  <h2>迟到桶</h2>
  <p class="muted">关窗后到达进桶；补入/作废为空桩，题面须择一写路径。</p>
  <p>合计 {{lateSummary.count||0}} 笔 / 金额 {{lateSummary.amount||0}}</p>
  <table>
    <thead><tr><th>窗口</th><th>键</th><th>时间</th><th>金额</th><th>原因</th><th>操作</th></tr></thead>
    <tbody>
      <tr v-for="e in lateItems" :key="'l'+e.id">
        <td>{{e.window_name}}</td>
        <td>{{e.biz_key}}</td>
        <td>{{e.event_ts}}</td>
        <td>{{e.amount}}</td>
        <td>{{e.reason}}</td>
        <td>
          <button class="ghost" @click="promoteLate(e.id)">补入空桩</button>
          <button class="ghost" @click="discardLate(e.id)">作废空桩</button>
        </td>
      </tr>
    </tbody>
  </table>
</div>
`;
