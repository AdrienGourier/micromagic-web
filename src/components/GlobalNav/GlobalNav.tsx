import './GlobalNav.css'

const navItems = [
  { name: 'Tienda', href: '/tienda' },
  { name: 'La Esponja', href: '/esponja' },
  { name: 'La Mopa', href: '/mopa' },
  { name: 'Accesorios', href: '/accesorios' },
  { name: 'Nuestros Distribuidores', href: '/distribuidores' },
  { name: 'Contacto & ayuda', href: '/contacto' },
]

export function GlobalNav() {
  return (
    <div id="globalheader">
      <nav id="globalnav" className="globalnav">
        <div className="globalnav-content">
          <ul className="globalnav-list">
            {/* Logo */}
            <li className="globalnav-item globalnav-item-logo">
              <a href="/" className="globalnav-link globalnav-link-logo">
                <span className="globalnav-logo-text">Micromagic</span>
              </a>
            </li>

            {/* Menu Items */}
            <li className="globalnav-item globalnav-menu">
              <div className="globalnav-menu-list">
                {navItems.map((item) => (
                  <div key={item.name} className="globalnav-item globalnav-item-menu">
                    <a href={item.href} className="globalnav-link">
                      <span className="globalnav-link-text">{item.name}</span>
                    </a>
                  </div>
                ))}
              </div>
            </li>

            {/* Search Icon */}
            <li className="globalnav-item globalnav-search">
              <a href="/buscar" className="globalnav-link globalnav-link-search" aria-label="Buscar">
                <svg height="44" viewBox="0 0 15 44" width="15" xmlns="http://www.w3.org/2000/svg">
                  <path d="M14.298,27.202l-3.87-3.87c0.701-0.929,1.122-2.081,1.122-3.332c0-3.06-2.489-5.55-5.55-5.55c-3.06,0-5.55,2.49-5.55,5.55c0,3.061,2.49,5.55,5.55,5.55c1.251,0,2.403-0.421,3.332-1.122l3.87,3.87c0.151,0.151,0.35,0.228,0.548,0.228s0.396-0.076,0.548-0.228C14.601,27.995,14.601,27.505,14.298,27.202z M1.55,20c0-2.454,1.997-4.45,4.45-4.45c2.454,0,4.45,1.997,4.45,4.45S8.454,24.45,6,24.45C3.546,24.45,1.55,22.454,1.55,20z" fill="currentColor"/>
                </svg>
              </a>
            </li>

            {/* Cart Icon */}
            <li className="globalnav-item globalnav-bag">
              <a href="/carrito" className="globalnav-link globalnav-link-bag" aria-label="Carrito">
                <svg height="44" viewBox="0 0 14 44" width="14" xmlns="http://www.w3.org/2000/svg">
                  <path d="m11.3535 16.0283h-1.0205a3.4229 3.4229 0 0 0 -3.333-2.9648 3.4229 3.4229 0 0 0 -3.333 2.9648h-1.02a2.1184 2.1184 0 0 0 -2.117 2.1162v7.7155a2.1186 2.1186 0 0 0 2.1162 2.1167h8.707a2.1186 2.1186 0 0 0 2.1168-2.1167v-7.7155a2.1184 2.1184 0 0 0 -2.1165-2.1162zm-4.3535-1.8652a2.3169 2.3169 0 0 1 2.2222 1.8652h-4.4444a2.3169 2.3169 0 0 1 2.2222-1.8652zm5.37 11.6969a1.0182 1.0182 0 0 1 -1.0166 1.0171h-8.7069a1.0182 1.0182 0 0 1 -1.0165-1.0171v-7.7155a1.0178 1.0178 0 0 1 1.0166-1.0166h8.707a1.0178 1.0178 0 0 1 1.0164 1.0166z" fill="currentColor"/>
                </svg>
              </a>
            </li>
          </ul>
        </div>
      </nav>
      <div className="globalnav-placeholder"></div>
    </div>
  )
}
