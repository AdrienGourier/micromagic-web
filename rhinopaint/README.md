# rhinopaint.es

Copia estática del WordPress + WooCommerce que vivía en el webspace de IONOS.
Se sirve desde S3 + CloudFront en la cuenta AWS de Rhino (088668667991, perfil
`rhino`), stack `rhinopaint-web` (us-east-1). En servicio desde el 03/11/2026.

- `sitio/`: la web tal cual se sube. **Es el original**: el WordPress de IONOS
  desaparece el 27/12/2026 y después ya no se puede volver a copiar.
- `template.yaml`: certificado, bucket privado, CloudFront y la función de rutas
  (www al dominio raíz, `/ruta` → `/ruta/index.html`, carrito, pago y cuenta →
  `/contactar`).
- `../dns-rhinopaint.yaml`: zona de Route 53 (stack `rhinopaint-dns`); los
  registros de la web son alias de la distribución.

## Qué cambia respecto a la web de IONOS

- Sin tienda: «Añadir al carrito» pasa a «Pedir presupuesto» (→ `/contactar`), y
  el carrito y «Mi cuenta» desaparecen del menú.
- Sin formulario: `/contactar` da el correo `info@rhinopaint.es` (buzón en
  forwardemail).
- Sin comentarios, buscador ni estadísticas de Jetpack.
- Las imágenes, el núcleo de WordPress y WooCommerce se sirven desde aquí, no
  desde el CDN de WordPress.com. Solo `/principal` (contenido de ejemplo del
  tema) enlaza 3 fotos de demo de fuera.
- Las fuentes cargan. En IONOS no cargaban: se pedían por `http://` dentro de una
  página `https://` y el navegador las bloqueaba.

## Cambiar algo

Editar el HTML de `sitio/` y subir:

```bash
python3 rhinopaint/scripts/probar-local.py rhinopaint/sitio   # 0 que faltan, 0 restos de la tienda
./rhinopaint/scripts/desplegar.sh                              # S3 + invalidación de CloudFront
```

`scripts/copiar-web.py --salida rhinopaint/sitio` vuelve a copiar la web desde
IONOS. Solo sirve hasta el 27/12/2026.
