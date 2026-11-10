import { fetchProducts } from '../lib/api';
import { ProductCard } from '../components/ProductCard';

export default async function HomePage() {
  const products = await fetchProducts();
  return (
    <main>
      <h1>ShopFlow</h1>
      <section className="grid">
        {products.map((p) => <ProductCard key={p.sku} product={p} onAdd={() => {}} />)}
      </section>
    </main>
  );
}
