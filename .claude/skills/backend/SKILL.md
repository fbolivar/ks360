---
name: backend
description: "Agent especializado en Server Actions, API routes, logica de negocio, y conexiones con servicios externos. Se activa automaticamente cuando la tarea involucra Server Actions, API routes, integraciones, webhooks, cron jobs, o logica del lado del servidor."
user-invocable: false
context: fork
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Agent: Backend

> Especialista en logica del lado del servidor dentro del Golden Path.

---

## Dominio

- **Server Actions** (`"use server"`) en `src/features/*/services/`
- **API Routes** en `src/app/api/`
- **Webhooks** (Polar, Supabase, externos)
- **Middleware** en `src/middleware.ts`
- **Integraciones** con servicios externos (APIs, SDKs)
- **Validacion server-side** con Zod

---

## Patrones Obligatorios

### Server Actions (preferido sobre API routes)

```typescript
"use server"

import { createClient } from "@/shared/lib/supabase/server"
import { z } from "zod"

const schema = z.object({ /* ... */ })

export async function myAction(formData: FormData) {
  const parsed = schema.safeParse(Object.fromEntries(formData))
  if (!parsed.success) return { error: "Datos invalidos" }

  const supabase = await createClient()
  // ... logica
}
```

### API Routes (solo cuando Server Actions no aplican)

Usar API routes unicamente para:
- Webhooks de servicios externos
- Endpoints consumidos por terceros
- Streaming responses
- Cron jobs

```typescript
// src/app/api/webhook/route.ts
import { NextRequest, NextResponse } from "next/server"

export async function POST(req: NextRequest) {
  // Validar signature del webhook
  // Procesar payload
  return NextResponse.json({ ok: true })
}
```

### Supabase Server Client

```typescript
import { createClient } from "@/shared/lib/supabase/server"

// SIEMPRE usar el client de server en Server Actions/API routes
const supabase = await createClient()
```

---

## Checklist de Calidad

- [ ] Toda entrada de usuario validada con Zod
- [ ] Supabase client de server (nunca el de browser)
- [ ] RLS habilitado en todas las tablas
- [ ] Secrets en variables de entorno, nunca en codigo
- [ ] Error handling con mensajes user-friendly
- [ ] Server Actions en `services/`, no en componentes

---

## Cuando Escalar

- Si la tarea requiere cambios en UI → delegar a agent `frontend`
- Si requiere migraciones SQL → delegar a skill `supabase`
- Si es compleja (4+ archivos) → sugerir `bucle-agentico`
