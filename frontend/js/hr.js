// HR 總覽頁（FR-009～FR-014、FR-019、FR-067～FR-072）。
//
// 這個畫面刻意沒有「檢視 AI 報告」或「檢視內部評語」的入口——
// 不是因為隱藏，而是因為後端根本不會回傳這些欄位（FR-008）。

import { requireSession, handleAuthFailure, getProfile } from './session.js';
import {
  hr,
  ApiError,
  STATUS_LABELS,
  DECISION_LABELS,
  EMAIL_STATUS_LABELS,
} from './api.js';

const rows = document.getElementById('assessment-rows');
const emptyHint = document.getElementById('empty-hint');
const filterForm = document.getElementById('filter-form');
const dialogCreate = document.getElementById('dialog-create');
const dialogNotify = document.getElementById('dialog-notify');

let notifyTargetId = null;

function textCell(value) {
  const cell = document.createElement('td');
  cell.className = 'px-4 py-2';
  cell.textContent = value ?? '—';
  return cell;
}

function actionButton(label, handler) {
  const button = document.createElement('button');
  button.className = 'rounded border border-slate-300 px-2 py-1 text-xs mr-1';
  button.textContent = label;
  button.addEventListener('click', handler);
  return button;
}

function renderRow(item) {
  const tr = document.createElement('tr');
  tr.className = 'border-t border-slate-100';
  tr.append(
    textCell(item.name),
    textCell(item.job_title),
    textCell(item.dept_id),
    textCell(item.assigned_manager),
    textCell(STATUS_LABELS[item.status] || item.status),
    textCell(item.final_decision ? DECISION_LABELS[item.final_decision] : '—'),
    textCell(EMAIL_STATUS_LABELS[item.email_status] || item.email_status),
  );

  const actions = document.createElement('td');
  actions.className = 'px-4 py-2 whitespace-nowrap';
  actions.append(
    actionButton('重新產生連結', () => regenerate(item.id)),
  );
  // 通知僅在已決策後才有意義（FR-067）
  if (item.status === 'DECIDED') {
    actions.append(actionButton('發送通知', () => openNotify(item.id)));
  }
  tr.append(actions);
  return tr;
}

async function refresh() {
  const filters = {
    dept_id: document.getElementById('filter-dept').value,
    status: document.getElementById('filter-status').value,
    job_title: document.getElementById('filter-job').value.trim(),
  };

  try {
    const items = await hr.listAssessments(filters);
    rows.replaceChildren(...items.map(renderRow));
    emptyHint.classList.toggle('hidden', items.length > 0);
  } catch (error) {
    reportError(error);
  }
}

async function loadDepartments() {
  try {
    const departments = await hr.listDepartments();
    const filterSelect = document.getElementById('filter-dept');
    const createSelect = document.getElementById('create-dept');
    for (const dept of departments) {
      filterSelect.append(new Option(dept.name, dept.id));
      createSelect.append(new Option(dept.name, dept.id));
    }
  } catch (error) {
    reportError(error);
  }
}

async function regenerate(id) {
  try {
    const result = await hr.regenerateToken(id);
    // 舊連結已立即失效（FR-019），因此必須把新連結交給操作者
    window.prompt('新的專屬連結（舊連結已失效）：', result.candidate_url || result.token);
    await refresh();
  } catch (error) {
    reportError(error);
  }
}

// ── 新增考核 ──────────────────────────────────────────────────────────

document.getElementById('btn-new').addEventListener('click', () => {
  document.getElementById('create-error').classList.add('hidden');
  document.getElementById('create-form').reset();
  dialogCreate.showModal();
});

document.getElementById('create-cancel').addEventListener('click', () => dialogCreate.close());

document.getElementById('create-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const errorBox = document.getElementById('create-error');

  const submit = async (confirmDuplicate) =>
    hr.createAssessment({ ...payload, confirm_duplicate: confirmDuplicate });

  try {
    const created = await submit(false);
    finishCreate(created);
  } catch (error) {
    // 重複邀請必須由 HR 明確確認後才建立（FR-009 邊界情況）
    if (error instanceof ApiError && error.code === 'DUPLICATE_ASSESSMENT') {
      if (window.confirm(`${error.message}\n\n仍要建立新的考核紀錄嗎？`)) {
        try {
          finishCreate(await submit(true));
          return;
        } catch (retryError) {
          reportInline(errorBox, retryError);
          return;
        }
      }
      return;
    }
    reportInline(errorBox, error);
  }
});

function finishCreate(created) {
  dialogCreate.close();
  window.prompt('專屬測驗連結（請寄送給應徵者）：', created.candidate_url || created.token);
  refresh();
}

// ── 結果通知（FR-067～FR-072）──────────────────────────────────────────

async function openNotify(id) {
  notifyTargetId = id;
  const status = document.getElementById('notify-status');
  status.classList.add('hidden');
  try {
    const draft = await hr.previewNotification(id);
    const form = document.getElementById('notify-form');
    form.subject.value = draft.subject;
    form.body.value = draft.body;
    dialogNotify.showModal();
  } catch (error) {
    reportError(error);
  }
}

document.getElementById('notify-cancel').addEventListener('click', () => dialogNotify.close());

document.getElementById('notify-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.getElementById('notify-status');
  try {
    const result = await hr.sendNotification(notifyTargetId, form.subject.value, form.body.value);
    status.classList.remove('hidden');
    if (result.email_status === 'SENT') {
      status.className = 'text-sm text-green-700';
      status.textContent = '已寄送。';
      dialogNotify.close();
    } else {
      // 寄送失敗不是例外，HR 可重新發送（FR-072）
      status.className = 'text-sm text-red-600';
      status.textContent = `寄送失敗：${result.email_error || '未知原因'}。可再次嘗試發送。`;
    }
    refresh();
  } catch (error) {
    reportInline(status, error);
  }
});

// ── 錯誤呈現 ──────────────────────────────────────────────────────────

function reportInline(element, error) {
  element.classList.remove('hidden');
  element.className = element.className.replace(/hidden/, '') + ' text-sm text-red-600';
  element.textContent = error instanceof ApiError ? error.message : '操作失敗，請稍後再試。';
}

function reportError(error) {
  // 權杖過期就回登入頁；以前這裡只能 alert「請先登入」，因為還沒有登入頁
  if (error instanceof ApiError && handleAuthFailure(error.status)) return;
  window.alert(error instanceof ApiError ? error.message : '操作失敗，請稍後再試。');
}

filterForm.addEventListener('submit', (event) => {
  event.preventDefault();
  refresh();
});

if (requireSession()) {
  const profile = getProfile();
  document.getElementById('current-user').textContent = profile ? `${profile.name}｜HR` : 'HR';
  loadDepartments().then(refresh);
}
