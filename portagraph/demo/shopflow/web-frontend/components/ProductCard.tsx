import type { Product } from '../lib/api';

export function ProductCard({ product, onAdd }: { product: Product; onAdd: (sku: string) => void }) {
  return (
    <article className="card">
      <h3>{product.title}</h3>
      <p>{product.price.toLocaleString('ru-RU')} ₽</p>
      <button disabled={product.stock === 0} onClick={() => onAdd(product.sku)}>В корзину</button>
    </article>
  );
}
