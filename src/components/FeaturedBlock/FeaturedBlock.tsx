import './FeaturedBlock.css'

interface FeaturedBlockProps {
  title: string
  subtitle?: string
  price?: string
  imageUrl?: string
  imageAlt?: string
  href: string
}

export function FeaturedBlock({ title, subtitle, price, imageUrl, imageAlt, href }: FeaturedBlockProps) {
  return (
    <article className="featured-block">
      <a href={href} className="featured-block-link">
        <div className="featured-block-image">
          {imageUrl ? (
            <img src={imageUrl} alt={imageAlt || title} className="featured-block-img" />
          ) : (
            <div className="featured-block-placeholder">
              <span>Imagen del producto</span>
            </div>
          )}
        </div>
        <div className="featured-block-content">
          <h3 className="featured-block-title">{title}</h3>
          {subtitle && <p className="featured-block-subtitle">{subtitle}</p>}
          {price && <p className="featured-block-price">{price}</p>}
        </div>
      </a>
    </article>
  )
}
