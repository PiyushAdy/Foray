import { renderTotals } from './render.js';
import { fetchTotals, fetchAccounts } from './api.js';

const root = document.getElementById('ledger');
const state = { accounts: [], totals: {} };

async function refresh() {
  state.accounts = await fetchAccounts();
  state.totals = await fetchTotals();
  root.innerHTML = renderTotals(state);
}

document.addEventListener('DOMContentLoaded', refresh);
window.ledgerline = { refresh, state };
export { refresh };
