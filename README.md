# micromagic-web

`micromagic.tv` reconstruido como sitio estático, para sacarlo del WordPress de
IONOS. Astro → S3 → CloudFront. Sin PHP, sin MySQL, sin WooCommerce: la tienda
llevaba **cero pedidos en 12 meses** y el contacto real de la web es WhatsApp,
así que no hay backend que mantener.

Contexto completo del recorte de gasto: `~/.claude/plans/glistening-churning-valley.md`.

## Puesta en marcha

```bash
cd ~/cop/micromagic-web
npm install
npm run dev          # http://localhost:4321
```

## Rehacer el contenido desde el WordPress antiguo

Los tres pasos dependen unos de otros; este script los encadena en el orden bueno:

```bash
./scripts/actualizar-contenido.sh
```

| Script | Qué hace |
|---|---|
| `extraer-wp.py` | Saca las páginas publicadas de la BD a `src/content/paginas/*.md`. Descarta la fontanería de WooCommerce y el relleno lorem ipsum de la plantilla. Si una página está vacía en la BD (la portada la monta el tema), descarga el HTML servido. |
| `extraer-imagenes.py` | Saca los originales de `~/Backups/ionos-2026-09-18/` y reapunta las rutas del Markdown. |
| `optimizar-imagenes.sh` | Borra las que nadie referencia y reduce el resto a 1600 px. **187 MB → 19 MB.** |

`extraer-wp.py` lee la BD viva por `ssh ionos`. Cuando IONOS se cancele, restaura
el volcado de `~/Backups/ionos-2026-09-18/db/` en un MySQL local y apunta el
script ahí — pero para entonces el contenido ya estará en git y no hará falta.

## Desplegar

Requiere una cuenta AWS propia de INNOVACION RHINO S.L. con el perfil `rhino`
configurado. **Nunca la cuenta personal 289938130842.**

```bash
# 1. certificado (CloudFront solo lee ACM de us-east-1)
aws acm request-certificate --domain-name micromagic.tv \
  --subject-alternative-names www.micromagic.tv \
  --validation-method DNS --region us-east-1 --profile rhino

# 2. ver qué registros CNAME hay que crear en el panel de IONOS
aws acm describe-certificate --certificate-arn <arn> --region us-east-1 \
  --profile rhino --query 'Certificate.DomainValidationOptions[].ResourceRecord'

# 3. con el certificado ya "ISSUED", crear la infraestructura
aws cloudformation deploy --template-file template.yaml \
  --stack-name micromagic-web --region us-east-1 --profile rhino \
  --parameter-overrides CertificadoArn=<arn>

# 4. publicar
./scripts/desplegar.sh
```

El paso 2 hay que hacerlo a mano en IONOS: el dominio sigue registrado allí y
solo se cambian los DNS. La validación no termina hasta que esos CNAME existen.

## Cambio de DNS

1. Probar todo en la URL de CloudFront **antes** de tocar nada.
2. En IONOS, bajar el TTL a 300 s y esperar a que caduque el anterior.
3. Apuntar `micromagic.tv` y `www` a la distribución.
4. Dejar el WordPress en pie una semana como marcha atrás.

## Decisiones que conviene no deshacer sin pensarlo

- **Las URLs se conservan.** Los 5.415 visitantes únicos mensuales llegan por
  Google. `src/pages/[...slug].astro` genera cada página con el slug que tenía
  en WordPress, y la CloudFront Function manda al inicio las URLs muertas de la
  tienda con un 301.
- **La paleta sale de las fotos del producto**, no de una tendencia: el blanco
  del panel, el gris de la melamina, el rojo del roce que se elimina.
- **Una sola tipografía**, Archivo, jugando con su eje de anchura. Los titulares
  van expandidos y pesados como el estampado de las cajas.
- **La portada tiene un solo momento llamativo**: el fotograma sucio se borra de
  verdad al pasar el dedo. Son dos fotogramas reales del mismo panel. Funciona
  con teclado mediante el botón «Ver el resultado» y respeta `prefers-reduced-motion`.

## Pendiente

- Repasar a mano `home.md` y `blog-2.md`: vienen del HTML servido y arrastran
  restos de configuración de los carruseles del tema.
- Decidir qué hacer con `homepage.md`, que duplica `pack-de-5-unidades.md`.
