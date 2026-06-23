---
name: sprint
description: "Ejecutar tareas rapidas y simples que no requieren fases ni PRP. Activar cuando la tarea es clara, toca 1-3 archivos, se puede completar en una sola iteracion, y NO necesita planificacion compleja. Ejemplos: corregir un bug, ajustar estilos, agregar un campo, cambiar un texto, refactorizar una funcion."
argument-hint: "[descripcion de la tarea]"
---

# Sprint: Tareas Rapidas

> "No todo necesita un plan. A veces solo hay que hacerlo."

Sprint es el complemento de `bucle-agentico`. Mientras el bucle es para features complejas multi-fase, Sprint es para tareas que se resuelven en minutos.

---

## Cuando Usar Sprint (vs Bucle Agentico)

| Criterio | Sprint | Bucle Agentico |
|----------|--------|----------------|
| Archivos afectados | 1-3 | 4+ |
| Requiere DB + UI + API | No | Si |
| Fases dependientes | No | Si |
| Necesita PRP | No | Si |
| Tiempo estimado | Minutos | Horas |

### Ejemplos de Sprint

```
"Cambia el color del boton de login a azul"
"Agrega validacion al campo email"
"Corrige el typo en el dashboard"
"Mueve el componente X a shared/"
"Agrega un campo 'phone' al formulario de registro"
"El boton de logout no funciona"
"Refactoriza esta funcion para usar async/await"
```

---

## Flujo Sprint: 4 Pasos

### 1. ENTENDER

- Leer el request del usuario
- Identificar archivo(s) afectados
- Si no es claro, preguntar UNA vez (no mas)

### 2. EXPLORAR

- Leer los archivos relevantes (maximo 3)
- Entender el patron existente
- Identificar el cambio minimo necesario

### 3. EJECUTAR

- Hacer el cambio
- Seguir el patron existente del codebase
- No refactorizar codigo que no esta relacionado
- No agregar features extra que no se pidieron

### 4. VALIDAR

- Verificar que no hay errores de TypeScript (si aplica)
- Si es visual, tomar screenshot con Playwright
- Si es logica, verificar con Next.js MCP
- Reportar al usuario: que se hizo, donde

---

## Reglas

1. **Minimalismo**: El cambio mas pequeno que resuelve el problema
2. **Sin scope creep**: Solo lo que se pidio, nada mas
3. **Respetar patrones**: Seguir las convenciones existentes del proyecto
4. **Reportar rapido**: Un resumen de 1-2 lineas al terminar

---

## Escalacion Automatica

Si durante el sprint descubres que la tarea es mas compleja de lo esperado:

```
Sprint detecta complejidad
    |
    ├── Toca 4+ archivos → Sugerir PRP + Bucle Agentico
    ├── Requiere migracion DB → Sugerir PRP + Bucle Agentico
    └── Tiene dependencias entre cambios → Sugerir PRP + Bucle Agentico
```

Informar al usuario: "Esta tarea es mas compleja de lo que parece. Recomiendo usar /prp para planificarla primero."

---

*"La velocidad viene de saber cuando NO planificar."*
