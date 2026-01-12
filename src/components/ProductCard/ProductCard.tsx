import './ProductCard.css'

interface ProductCardProps {
  title: string
  subtitle?: string
  price: string
  imageUrl?: string
  imageAlt: string
  href: string
}

export function ProductCard({ title, subtitle, price, imageUrl, imageAlt, href }: ProductCardProps) {
  return (
    <article className="product-card">
      <a href={href} className="product-card-link">
        <div className="product-card-image-container">
          {imageUrl ? (
            <img src={imageUrl} alt={imageAlt} className="product-card-image" />
          ) : (
            <div className="product-card-placeholder">
              <span>Imagen de {title}</span>
            </div>
          )}
        </div>
        <div className="product-card-content">
          <h3 className="product-card-title">{title}</h3>
          {subtitle && <p className="product-card-subtitle">{subtitle}</p>}
          <p className="product-card-price">{price}</p>
        </div>
      </a>
    </article>
  )
}
