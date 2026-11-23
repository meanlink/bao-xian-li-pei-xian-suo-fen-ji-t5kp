import {get, post} from '../api.js';
import {Layout, Section, StatCard, openModal, showToast} from '../components/ui.js';
import {dateText, entryKind, escapeHtml, money, monthText, reportStatus, todayText} from '../utils/constants.js';

export async function renderMonthlyReports(user, navigate) {
  const data = await get('/monthly-reports');
  const canManage = user.role === 'risk_manager';
  const {items, missing_records: missing, pending_carry: pendingCarry} = data;

  const rows = items.map(item => `<tr>
    <td><div class="claim-id">${monthText(item.month)}</div>
      <div class="subline">${item.status === 'frozen' ? `冻结于 ${dateText(item.frozen_at)} · ${escapeHtml(item.frozen_by || '-')}` : '实时汇总，冻结后定格'}</div></td>
    <td><span class="badge ${item.status === 'frozen' ? 'badge-mint' : 'badge-amber'}">${reportStatus[item.status]}</span></td>
    <td><b>${item.closed_count}</b> 件</td>
    <td>${money(item.loss_total)}</td>
    <td>${item.carry_count ? `<b>${item.carry_count}</b> 件 / ${money(item.carry_total)}` : '-'}</td>
    <td><div class="actions">
      <button class="btn btn-soft" data-entries="${item.month}">明细</button>
      ${canManage && item.status === 'open' ? `<button class="btn btn-primary" data-freeze="${item.month}">冻结月报</button>` : ''}
    </div></td>
  </tr>`).join('');

  const missingRows = missing.items.map(item => `<tr>
    <td><button class="triage-claim" data-nav="detail" data-detail="${item.id}">${escapeHtml(item.claim_no)}</button></td>
    <td><b>${escapeHtml(item.customer_name)}</b></td>
    <td>${money(item.loss_amount)}</td>
    <td>${dateText(item.updated_at)}</td>
    <td>${canManage ? `<button class="btn btn-soft" data-backfill="${item.id}" data-claim-no="${escapeHtml(item.claim_no)}">补登核赔日</button>` : '<span class="subline">待主管补登</span>'}</td>
  </tr>`).join('');

  const carryRows = pendingCarry.items.map(item => `<tr>
    <td><button class="triage-claim" data-nav="detail" data-detail="${item.claim_id}">${escapeHtml(item.claim_no)}</button></td>
    <td><b>${escapeHtml(item.customer_name)}</b></td>
    <td>${dateText(item.settled_on)}</td>
    <td><span class="badge badge-amber">${monthText(item.attribution_month)}</span></td>
    <td>${money(item.loss_amount)}</td>
  </tr>`).join('');

  const content = `
    <header class="page-head">
      <div><h1 class="page-title">核赔月报</h1>
      <p class="page-subtitle">按核赔日归月统计结案件数与报损金额。月报冻结后定格，迟到的结案作为差额记入随后冻结的月报。</p></div>
    </header>
    <div class="grid grid-3">
      ${StatCard('待核案件', missing.count, '已结案但缺少核赔记录', '!', 'amber')}
      ${StatCard('待结转差额', `${pendingCarry.count} 件`, `归属月已冻结 · 合计 ${money(pendingCarry.loss_total)}`, '↪', 'red')}
      ${StatCard('已冻结月报', items.filter(i => i.status === 'frozen').length, `当前业务月 ${monthText(data.business_month)}`, '▦', 'mint')}
    </div>
    <div style="margin-top:18px">${Section('月度报表', `
      <div class="table-wrap"><table class="table"><thead><tr>
        <th>月份</th><th>状态</th><th>结案件数</th><th>报损金额</th><th>差额结转</th><th>操作</th>
      </tr></thead><tbody>${rows || '<tr><td colspan="6" class="empty">暂无核赔记录</td></tr>'}</tbody></table></div>`)}
    </div>
    <div class="grid grid-2" style="margin-top:18px">
      ${Section('待核案件 · 缺少核赔记录', missing.count ? `
        <div class="notice" style="margin-bottom:12px">以下旧案件已结案但查不到核赔记录，不计入任何月份。补登核赔日后按核赔日归月。</div>
        <div class="table-wrap"><table class="table"><thead><tr>
          <th>案号</th><th>客户</th><th>报损金额</th><th>结案时间</th><th>操作</th>
        </tr></thead><tbody>${missingRows}</tbody></table></div>` : '<p class="empty">所有已结案案件都有核赔记录。</p>')}
      ${Section('待结转差额 · 归属月已冻结', pendingCarry.count ? `
        <div class="notice" style="margin-bottom:12px">以下结案记录的归属月已冻结，将记入随后第一份冻结的月报。</div>
        <div class="table-wrap"><table class="table"><thead><tr>
          <th>案号</th><th>客户</th><th>核赔日</th><th>归属月</th><th>报损金额</th>
        </tr></thead><tbody>${carryRows}</tbody></table></div>` : '<p class="empty">当前没有等待结转的差额记录。</p>')}
    </div>`;

  setTimeout(() => bindReports(navigate), 0);
  return Layout({user, active: 'monthlyReports', onNavigate: navigate, content});
}

function bindReports(navigate) {
  document.querySelectorAll('[data-entries]').forEach(button => {
    button.onclick = () => openEntries(button.dataset.entries);
  });
  document.querySelectorAll('[data-freeze]').forEach(button => {
    button.onclick = () => confirmFreeze(button.dataset.freeze, navigate);
  });
  document.querySelectorAll('[data-backfill]').forEach(button => {
    button.onclick = () => openBackfill(button.dataset.backfill, button.dataset.claimNo, navigate);
  });
}

async function openEntries(month) {
  const report = await get(`/monthly-reports/${month}`);
  const rows = report.entries.map(entry => `<tr>
    <td><div class="claim-id">${escapeHtml(entry.claim_no)}</div><div class="subline">${escapeHtml(entry.customer_name)}</div></td>
    <td>${dateText(entry.settled_on)}</td>
    <td><span class="badge ${entry.entry_kind === 'carry' ? 'badge-amber' : 'badge-blue'}">${monthText(entry.attribution_month)}</span></td>
    <td><span class="badge ${entry.entry_kind === 'carry' ? 'badge-red' : 'badge-mint'}">${entryKind[entry.entry_kind]}</span></td>
    <td>${money(entry.loss_amount)}</td>
  </tr>`).join('');
  openModal(`${monthText(month)}月报明细`, `
    <div class="kv" style="margin-bottom:16px">
      <div class="kv-item"><small>状态</small><b>${reportStatus[report.status]}${report.frozen_by ? ` · ${escapeHtml(report.frozen_by)}` : ''}</b></div>
      <div class="kv-item"><small>当月结案</small><b>${report.closed_count} 件 / ${money(report.loss_total)}</b></div>
      <div class="kv-item"><small>差额结转</small><b>${report.carry_count} 件 / ${money(report.carry_total)}</b></div>
    </div>
    ${report.status === 'open' ? '<div class="notice" style="margin-bottom:12px">月报未冻结，以下为实时预览，冻结后定格。</div>' : ''}
    <div class="table-wrap"><table class="table"><thead><tr>
      <th>案号</th><th>核赔日</th><th>归属月</th><th>类型</th><th>报损金额</th>
    </tr></thead><tbody>${rows || '<tr><td colspan="5" class="empty">本月暂无入账记录</td></tr>'}</tbody></table></div>`);
}

function confirmFreeze(month, navigate) {
  const modal = openModal(`冻结 ${monthText(month)} 月报`, `
    <p class="muted">冻结后该月结案件数与报损金额定格，不再变化。之后归属该月的结案会作为差额记入随后冻结的月报。冻结期间案件照常结案。</p>
    <div class="actions" style="margin-top:18px">
      <button class="btn btn-line" data-cancel>取消</button>
      <button class="btn btn-primary" data-confirm>确认冻结</button>
    </div>`);
  modal.querySelector('[data-cancel]').onclick = () => modal.remove();
  modal.querySelector('[data-confirm]').onclick = async event => {
    event.target.disabled = true;
    try {
      await post(`/monthly-reports/${month}/freeze`, {});
      modal.remove();
      showToast(`${monthText(month)}月报已冻结`);
      navigate('monthlyReports');
    } catch (err) {
      showToast(err.message);
      modal.remove();
      navigate('monthlyReports');
    }
  };
}

function openBackfill(claimId, claimNo, navigate) {
  const today = todayText();
  const modal = openModal(`补登核赔日 · ${claimNo}`, `
    <form class="form-grid">
      <p class="notice full">该案件已结案但缺少核赔记录。补登后按核赔日归月；若归属月已冻结，则作为差额记入随后冻结的月报。</p>
      <div class="field full"><label>实际核赔日</label>
        <input type="date" name="settled_on" value="${today}" max="${today}" required></div>
      <div class="full"><button type="submit" class="btn btn-primary">保存核赔记录</button></div>
    </form>`);
  modal.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.target));
    try {
      await post(`/claims/${claimId}/settlement-record`, body);
      modal.remove();
      showToast('核赔记录已补登');
      navigate('monthlyReports');
    } catch (err) {
      showToast(err.message);
    }
  };
}
