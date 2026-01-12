import './Footer.css'

const footerLinks = {
  shop: {
    title: 'Comprar',
    links: [
      { name: 'Tienda', href: '/tienda' },
      { name: 'La Esponja', href: '/esponja' },
      { name: 'La Mopa', href: '/mopa' },
      { name: 'Accesorios', href: '/accesorios' },
    ],
  },
  about: {
    title: 'Sobre Micromagic',
    links: [
      { name: 'Nuestra historia', href: '/historia' },
      { name: 'Distribuidores', href: '/distribuidores' },
    ],
  },
  help: {
    title: 'Ayuda',
    links: [
      { name: 'Contacto', href: '/contacto' },
      { name: 'Preguntas frecuentes', href: '/faq' },
    ],
  },
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-content">
        {/* Directory Links */}
        <div className="footer-directory">
          {Object.entries(footerLinks).map(([key, section]) => (
            <div key={key} className="footer-column">
              <h3 className="footer-column-title">{section.title}</h3>
              <ul className="footer-links">
                {section.links.map((link) => (
                  <li key={link.name}>
                    <a href={link.href} className="footer-link">
                      {link.name}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Legal */}
        <div className="footer-legal">
          <p className="footer-copyright">
            Copyright © {new Date().getFullYear()} Micromagic. Todos los derechos reservados.
          </p>
          <div className="footer-legal-links">
            <a href="/privacidad" className="footer-legal-link">Política de privacidad</a>
            <span className="footer-legal-separator">|</span>
            <a href="/terminos" className="footer-legal-link">Términos de uso</a>
          </div>
        </div>
      </div>
    </footer>
  )
}
