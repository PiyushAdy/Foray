import { formatAmount } from './format.js';

export function renderTotals(state) {
  if (!state.accounts.length) return '<p class="empty">No accounts yet</p>';
  const rows = state.accounts
    .map(a => `<tr><td>${a.id}</td><td>${a.name}</td><td class="num">${formatAmount(state.totals[a.id])}</td></tr>`)
    .join('');
  return `<table class="totals"><tbody>${rows}</tbody></table>`;
}
