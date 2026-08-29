const BASE = window.location.origin;

async function getJSON(path) {
  const response = await fetch(BASE + path);
  if (!response.ok) throw new Error(`request failed: ${path}`);
  return response.json();
}

export function fetchAccounts() {
  return getJSON('/accounts');
}

export function fetchTotals() {
  return getJSON('/totals');
}

export async function postEntry(entry) {
  const response = await fetch(BASE + '/entries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  return response.ok;
}
