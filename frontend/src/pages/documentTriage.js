import {get, post} from '../api.js';
import {Layout, Section, openModal, showToast} from '../components/ui.js';
import {canTriage, dateText, escapeHtml, money} from '../utils/constants.js';

const queues = {
  overdue: {label: '已逾期', badge: 'badge-red'},
  due_today: {label: '今日到期', badge: 'badge-amber'},
  unscheduled: {label: '待首次联系', badge: 'badge-gray'},
  scheduled: {label: '等待补件', badge: 'badge-blue'},
};
const channels = {phone: '电话', sms: '短信', email: '邮件'};
const triageDateTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short',
});

export async function renderDocumentTriage(user, navigate) {
  const {items, counts, business_date: today} = await get('/document-triage');
  const summary = Object.entries(queues).map(([id, {label, badge}]) => `
    <button class="triage-filter" type="button" data-bucket="${id}" aria-pressed="false">
      <span class="badge ${badge}">${label}</span><strong>${counts[id]}</strong>
    </button>`).join('');
  const content = `
    <header class="page-head">
      <div><h1 class="page-title">补件调度</h1>
      <p class="page-subtitle">先跟进已逾期和今日到期的案件。资料核齐后，案件离开队列并进入风险分级。</p></div>
      <div class="triage-date"><span>北京时间</span><b>${dateText(today)}</b></div>
    </header>
    ${Section('待补件案件', `
      <div class="triage-filters" role="group" aria-label="按补件进度筛选">${summary}</div>
      <div class="triage-list" id="triage-list">${items.map(renderQueueItem).join('')}</div>
      <p class="empty" id="triage-empty" ${items.length ? 'hidden' : ''}>当前没有符合条件的案件。受理缺少资料的新案件后会出现在这里。</p>`,
      `<button type="button" class="btn btn-line triage-filter-all" data-bucket="all" aria-pressed="true">显示全部 · ${items.length}</button>`)}
  `;
  setTimeout(() => bindQueue(items, today, navigate), 0);
  return Layout({user, active: 'documentTriage', onNavigate: navigate, content});
}

function renderQueueItem(item) {
  const {followup: record, bucket, claim_id: claimId} = item;
  const {label, badge} = queues[bucket];
  return `<article class="triage-row" data-queue="${bucket}">
    <div class="triage-identity">
      <button class="triage-claim" data-nav="detail" data-detail="${claimId}">${escapeHtml(item.claim_no)}</button>
      <strong>${escapeHtml(item.customer_name)}</strong>
      <span class="subline">${money(item.loss_amount)} · ${escapeHtml(item.claimant_phone)}</span>
    </div>
    <div class="triage-materials">
      <span class="subline">当前缺项</span>
      <ul>${item.missing_documents.map(doc => `<li>${escapeHtml(doc)}</li>`).join('')}</ul>
    </div>
    <div class="triage-deadline">
      <span class="badge ${badge}">${label}</span>
      ${record ? `<strong>补件期限 ${dateText(record.due_on)}</strong>
        <span class="subline">${dateText(record.contacted_on)} · ${channels[record.channel]} · ${escapeHtml(item.recorded_by_name)}</span>
        <p>${escapeHtml(record.contact_note)}</p>` : '<span class="subline">尚未约定补件日期</span>'}
    </div>
    <div class="triage-actions">
      <button type="button" class="btn btn-soft" data-contact="${claimId}">${record ? '登记再次联系' : '登记首次联系'}</button>
      <button type="button" class="btn btn-line" data-nav="detail" data-detail="${claimId}">进入资料核验</button>
    </div>
  </article>`;
}

function bindQueue(items, today, navigate) {
  const list = document.querySelector('#triage-list');
  if (!list) return;
  const filters = document.querySelectorAll('[data-bucket]');
  const rows = list.querySelectorAll('[data-queue]');
  for (const filter of filters) {
    filter.onclick = () => {
      const bucket = filter.dataset.bucket;
      filters.forEach(button => button.setAttribute('aria-pressed', button === filter));
      rows.forEach(row => {row.hidden = bucket !== 'all' && row.dataset.queue !== bucket;});
      document.querySelector('#triage-empty').hidden = Array.from(rows).some(row => !row.hidden);
    };
  }
  list.querySelectorAll('[data-contact]').forEach(button => {
    button.onclick = () => {
      const item = items.find(item => item.claim_id === Number(button.dataset.contact));
      openContactForm(item, today, navigate);
    };
  });
}

function openContactForm(item, today, navigate) {
  const record = item.followup;
  const modal = openModal(record ? '登记再次联系' : '登记首次联系', `
    <form class="form-grid triage-form">
      <p class="notice full"><b>${escapeHtml(item.claim_no)}</b><br>本次催收 ${item.missing_documents.map(escapeHtml).join('、')}</p>
      <div class="field full"><label for="triage-channel">联系渠道</label><select name="channel" id="triage-channel">
        ${Object.entries(channels).map(([key, label]) => `<option value="${key}">${label}</option>`).join('')}
      </select></div>
      <div class="field"><label for="triage-contacted">联系日期</label>
        <input type="date" name="contacted_on" id="triage-contacted" value="${today}" max="${today}" ${record ? `min="${dateText(record.contacted_on)}"` : ''} required></div>
      <div class="field"><label for="triage-due">补件期限</label>
        <input type="date" name="due_on" id="triage-due" min="${today}" required></div>
      <div class="field full"><label for="triage-note">联系结果</label>
        <textarea name="contact_note" id="triage-note" required minlength="6" maxlength="500" placeholder="记录沟通情况和约定的交付方式"></textarea></div>
      <p class="triage-error full" role="alert" hidden></p>
      <div class="full"><button type="submit" class="btn btn-primary">保存补件记录</button></div>
    </form>`);
  const form = modal.querySelector('form');
  form.elements.contacted_on.onchange = () => {form.elements.due_on.min = form.elements.contacted_on.value;};
  form.onsubmit = async event => {
    event.preventDefault();
    const save = form.querySelector('[type=submit]');
    const error = form.querySelector('[role=alert]');
    save.disabled = true;
    error.hidden = true;
    try {
      await post(`/claims/${item.claim_id}/document-followup`, {
        ...Object.fromEntries(new FormData(form)),
        followup_id: record?.id ?? null,
        expected_revision: record?.revision ?? 0,
        expected_missing_documents: item.missing_documents,
      });
      modal.remove();
      showToast('补件记录已保存');
      navigate('documentTriage');
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      save.disabled = false;
    }
  };
}

export function renderDocumentFollowup(user, claim, record) {
  if (!canTriage(user.role)) return '';
  const canFollowUp = ['intake', 'initial_review'].includes(claim.status)
    && claim.required_documents.some(doc => !claim.received_documents.includes(doc));
  if (!canFollowUp && !record) return '';
  const link = canFollowUp ? '<button class="btn btn-line" data-nav="documentTriage">打开补件调度</button>' : '';
  const complete = Boolean(record?.completed_at);
  const statusLabel = complete ? (canFollowUp ? '上次已核齐' : '已核齐') : '待补件';
  const body = record ? `<div class="triage-receipt" aria-label="补件回执">
    <span class="badge ${complete ? 'badge-mint' : 'badge-amber'}">${statusLabel}</span>
    <dl class="review-fields">
      <div><dt>跟进记录</dt><dd>第 ${record.revision} 次 · ${channels[record.channel]} · ${escapeHtml(record.recorded_by_name)}</dd></div>
      <div><dt>约定期限</dt><dd>${dateText(record.due_on)}</dd></div>
      <div><dt>上次催收</dt><dd>${record.requested_documents.map(escapeHtml).join('、')}</dd></div>
      ${complete ? `<div><dt>核齐时间与经办人</dt><dd>${triageDateTime.format(new Date(record.completed_at))} · ${escapeHtml(record.completed_by_name)}</dd></div>` : ''}
    </dl>
    <p>${escapeHtml(record.contact_note)}</p>
    ${complete && canFollowUp ? '<div class="notice">资料清单已更正，当前缺项待联系。</div>' : ''}
    ${complete && claim.status === 'initial_review' && !canFollowUp ? '<div class="notice">所需资料已核齐，风险主管可以运行分级。</div>' : ''}
  </div>` : '<p class="subline">尚无联系记录。前往补件调度登记催收情况与期限。</p>';
  return Section('补件跟进', body, link);
}
