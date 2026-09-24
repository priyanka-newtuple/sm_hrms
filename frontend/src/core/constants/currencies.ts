export interface CurrencyMeta {
  code: string;
  symbol: string;
  label: string;
}

export const CURRENCIES: CurrencyMeta[] = [
  { code: 'USD', symbol: '$',    label: 'US Dollar' },
  { code: 'EUR', symbol: '€',    label: 'Euro' },
  { code: 'GBP', symbol: '£',    label: 'British Pound' },
  { code: 'JPY', symbol: '¥',    label: 'Japanese Yen' },
  { code: 'INR', symbol: '₹',    label: 'Indian Rupee' },
  { code: 'AUD', symbol: 'A$',   label: 'Australian Dollar' },
  { code: 'CAD', symbol: 'C$',   label: 'Canadian Dollar' },
  { code: 'CHF', symbol: 'Fr',   label: 'Swiss Franc' },
  { code: 'CNY', symbol: '¥',    label: 'Chinese Yuan' },
  { code: 'SGD', symbol: 'S$',   label: 'Singapore Dollar' },
  { code: 'AED', symbol: 'د.إ',  label: 'UAE Dirham' },
  { code: 'MXN', symbol: 'MX$',  label: 'Mexican Peso' },
  { code: 'BRL', symbol: 'R$',   label: 'Brazilian Real' },
  { code: 'KRW', symbol: '₩',    label: 'South Korean Won' },
  { code: 'HKD', symbol: 'HK$',  label: 'Hong Kong Dollar' },
];
