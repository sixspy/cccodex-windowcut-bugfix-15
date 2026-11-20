export const materializeViewTemplate = `
<div class="card wide" v-show="tab===3">
  <h2>物化台账</h2>
  <p class="muted">分区失败策略为空桩（整窗回滚 vs 保留成功分区）。</p>
  <button class="ghost" @click="partitionStub">登记分区空桩</button>
  <table>
    <thead><tr><th>窗口</th><th>状态</th><th>行数</th><th>金额</th><th>分区</th><th>时间</th></tr></thead>
    <tbody>
      <tr v-for="m in mats" :key="m.id">
        <td>{{m.window_name}}</td>
        <td>{{m.status}}</td>
        <td>{{m.row_count}}</td>
        <td>{{m.total_amount}}</td>
        <td>{{m.partition_key}}</td>
        <td>{{m.created_at}}</td>
      </tr>
    </tbody>
  </table>
</div>
`;
