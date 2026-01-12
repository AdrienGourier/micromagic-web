import './HelpSection.css'

interface HelpBlockProps {
  title: string
  description: string
  href: string
}

function HelpBlock({ title, description, href }: HelpBlockProps) {
  return (
    <article className="help-block">
      <a href={href} className="help-block-link">
        <div className="help-block-icon">
          {/* Specialist Icon */}
          <svg width="54" height="54" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="27" cy="27" r="26" stroke="#1d1d1f" strokeWidth="2"/>
            <circle cx="27" cy="20" r="8" stroke="#1d1d1f" strokeWidth="2"/>
            <path d="M12 44c0-8.284 6.716-15 15-15s15 6.716 15 15" stroke="#1d1d1f" strokeWidth="2"/>
          </svg>
        </div>
        <div className="help-block-content">
          <h3 className="help-block-title">{title}</h3>
          <p className="help-block-text">{description}</p>
        </div>
      </a>
    </article>
  )
}

export function HelpSection() {
  return (
    <section className="help-section">
      <div className="container">
        <div className="section-header">
          <h2 className="headline">
            <span className="headline-primary">¿Necesitas ayuda?</span>{' '}
            <span className="headline-secondary">Donde y cuando quieras ;)</span>
          </h2>
        </div>
        
        <div className="help-blocks">
          <HelpBlock
            title="Especialistas Micromagic"
            description="Contacta con uno de nuestros especialistas profesionales."
            href="/contacto"
          />
        </div>
      </div>
    </section>
  )
}
