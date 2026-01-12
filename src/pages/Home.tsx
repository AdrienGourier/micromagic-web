import { ProductCard } from '../components/ProductCard'
import { FeaturedBlock } from '../components/FeaturedBlock'
import { HelpSection } from '../components/HelpSection'
import './Home.css'

const products = [
  {
    title: 'La Esponja',
    subtitle: 'Limpieza sin esfuerzo',
    price: 'Desde 9,99 €',
    href: '/productos/esponja',
    imageAlt: 'La Esponja Micromagic',
  },
  {
    title: 'La Mopa',
    subtitle: 'El poder de la limpieza',
    price: 'Desde 14,99 €',
    href: '/productos/mopa',
    imageAlt: 'La Mopa Micromagic',
  },
]

export function Home() {
  return (
    <main className="store-home">
      {/* Store Title */}
      <section className="store-title-section">
        <div className="container">
          <h1 className="store-title">Tienda</h1>
        </div>
      </section>

      {/* Products Grid */}
      <section className="products-section">
        <div className="container">
          <div className="products-grid">
            {products.map((product) => (
              <ProductCard
                key={product.title}
                title={product.title}
                subtitle={product.subtitle}
                price={product.price}
                href={product.href}
                imageAlt={product.imageAlt}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Latest Section */}
      <section className="latest-section">
        <div className="container">
          <div className="section-header">
            <h2 className="headline">
              <span className="headline-primary">Lo último.</span>{' '}
              <span className="headline-secondary">Echa un vistazo a lo nuevo de ahora.</span>
            </h2>
          </div>
          
          <div className="featured-blocks">
            <FeaturedBlock
              title="El nuevo pack de dos unidades"
              subtitle="Limpieza profesional"
              price="Desde 20 € el paquete"
              href="/productos/pack-dos"
            />
          </div>
        </div>
      </section>

      {/* Help Section */}
      <HelpSection />
    </main>
  )
}
