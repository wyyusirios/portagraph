const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://api-gateway:8080/api/v1';

export interface Product { sku: string; title: string; price: number; stock: number }

export async function fetchProducts(): Promise<Product[]> {
  const res = await fetch(`${API}/products`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Каталог недоступен');
  return res.json();
}

export async function createOrder(token: string, lines: { sku: string; quantity: number }[]) {
  const res = await fetch(`${API}/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(lines),
  });
  if (!res.ok) throw new Error('Не удалось оформить заказ');
  return res.json();
}
