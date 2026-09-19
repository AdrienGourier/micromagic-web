import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// Las páginas vienen del WordPress antiguo vía scripts/extraer-wp.py.
const paginas = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/paginas' }),
  schema: z.object({
    titulo: z.string(),
    slug: z.string(),
    tipo: z.enum(['page', 'post']),
    fecha: z.coerce.date(),   // YAML ya la entrega como Date
    orden: z.number().default(0),
    resumen: z.string().default(''),
    origen: z.enum(['bd', 'html-renderizado']).default('bd'),
  }),
});

export const collections = { paginas };
