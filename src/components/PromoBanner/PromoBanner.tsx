import './PromoBanner.css'

export function PromoBanner() {
  return (
    <div id="promo-banner" className="promo-banner">
      <div className="promo-banner-content">
        <p className="promo-banner-text">
          Conviértete en un distribuidor oficial de Micromagic → 40% de descuento en tu primer pedido.{' '}
          <a href="/distribuidores" className="promo-banner-link">
            Aprende más
          </a>
        </p>
      </div>
    </div>
  )
}
