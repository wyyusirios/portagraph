'use client';
import { useState } from 'react';
import { createOrder } from '../../lib/api';

export default function CartPage() {
  const [status, setStatus] = useState<string | null>(null);
  async function checkout() {
    try {
      const order = await createOrder(localStorage.getItem('token') ?? '', []);
      setStatus(`Заказ №${order.id} оформлен`);
    } catch (e) {
      setStatus((e as Error).message);
    }
  }
  return <main><h1>Корзина</h1><button onClick={checkout}>Оформить</button>{status && <p>{status}</p>}</main>;
}
