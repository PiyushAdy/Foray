const formatter = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

export function formatAmount(value) {
  if (value === undefined || value === null) return '-';
  return formatter.format(Number(value));
}
