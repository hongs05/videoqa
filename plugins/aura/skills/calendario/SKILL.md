---
description: Arma o revisa el calendario de contenido del mes. "Armar" convierte la estrategia (o las cantidades que le digas) en el Excel con el formato Aura; "revisar" compara un calendario contra la estrategia y dice qué falta o no cumple. Úsalo cuando la persona diga "ármame el calendario de octubre", "pásame esto a Excel", "revisa el calendario", "¿el calendario cumple la estrategia?".
allowed-tools: Read Write Bash(uv run:*) Bash(open:*) Bash(ls:*) Bash(cat:*)
---

# Calendario de contenido

La persona es **no técnica**: habla en español informal (tú), sin jerga, sin comandos a la vista.

Esta skill hace dos cosas. Primero decide cuál según lo que pida:

- **Armar** → "ármame el calendario", "pásame la estrategia a Excel", "hazme el de octubre".
- **Revisar** → "revisa el calendario", "¿esto cumple la estrategia?", "¿me faltó algo?".

Si no queda claro, pregúntale en una línea: "¿Quieres que **lo arme** desde la estrategia, o que **revise** uno que ya tienes?"

Antes de empezar, lee la referencia de formato con Read:
`${CLAUDE_PLUGIN_ROOT}/skills/calendario/references/formato.md`
(ahí están las cuentas, los tipos de contenido, las plataformas por cuenta y la regla de horario).

---

## MODO ARMAR

### Paso 1 — Conseguir los insumos
Necesitas, por cada cuenta: **qué piezas** van (tipos), **en qué fechas** y, si los hay, los **copys**.

- Si te da la **estrategia** (un documento, PDF o texto pegado): léela y saca de ahí, por cuenta, cuántas piezas de cada tipo y sus fechas/copys.
- Si te da **cantidades sueltas** ("Goldstone: 4 reels los sábados"): úsalas directo.
- Si falta algo clave (mes, año o cuentas), pregúntalo en una línea. No inventes fechas.

⚠️ **Mes correcto:** confirma que la estrategia es **del mismo mes** que vas a armar. Si ves señales de que es de otro mes, avísale antes de seguir (esto ya causó líos en Ancestral).

### Paso 2 — Construir el esqueleto
Arma un objeto `data` así: por cada cuenta, un mapa de **día → tipo(s)**. Si un día lleva varios, únelos con " / " en orden **Post / Reel / Storie**.

Tipos válidos (respeta estos nombres): **Reel, Carrusel, Storie, Storie interactiva, Post, Reel con CTA**.

### Paso 3 — Generar el Excel
Escribe un JSON temporal (con Write) con esta forma:

```json
{
  "year": 2026,
  "month": 10,
  "brands": ["Goldstone", "Ponchar", "..."],
  "data": { "Goldstone": {"3": "Reel", "10": "Reel / Post"} }
}
```

El **orden de `brands`** es el orden de las columnas. Guárdalo, por ejemplo, en `/tmp/calendario.json`. Luego:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/armar_calendario.py" /tmp/calendario.json "$HOME/Desktop/<Mes Año>.xlsx"
```

Si en `~/.videoqa/config.yaml` hay un `drive_root`, ofrécele guardarlo ahí en vez del Escritorio.

La primera vez, avisa: "Voy a armar el Excel, dame un momento." (uv instala lo necesario solo, una vez.)

### Paso 4 — Entregar
Abre el archivo y cuéntale en simple qué armaste:

```bash
open "$HOME/Desktop/<Mes Año>.xlsx"
```

> Listo, te armé **Octubre 2026** con 9 cuentas. Goldstone quedó con 4 reels (sábados) y 2 posts; Gloss con stories lun/mié/vie… Te lo abrí. Revísalo y si algo no cuadra, dime y lo ajusto.

Recuérdale que **ella es el control de calidad**: el Excel es un punto de partida para que ajuste, no la versión final.

---

## MODO REVISAR

### Paso 1 — Conseguir las dos cosas
Necesitas **el calendario** (Excel, esqueleto o lo que tenga) y **la estrategia** del mes. Si falta la estrategia, dile que sin ella solo puedes revisar lo formal (fechas, copys, ortografía), no si cumple.

### Paso 2 — Revisar (checklist)
Compara cuenta por cuenta:

1. **Cantidades y tipos:** ¿coinciden con la estrategia? (nº de reels, carruseles, stories…).
2. **Fechas y horario:** ¿fechas correctas del mes? Recuerda que se publica a las **7am hora Puerto Rico**.
3. **Copys:** ¿cada pieza tiene su copy? (un error real frecuente es publicar sin copy).
4. **Plataformas:** ¿está contemplada cada red según la cuenta? (LinkedIn y TikTok solo en las cuentas que aplican — ver formato.md).
5. **Ortografía y nombres:** nombres de marca/producto bien escritos.
6. **Mes correcto:** la estrategia usada es la del mes que se revisa (ojo con mezclas de meses).
7. **Cuentas sensibles:** en **NBU, Wanda García y Ancestral** revisa con más cuidado (son las de más cambios de última hora).

### Paso 3 — Reportar
Un resumen de una línea y luego el detalle por cuenta, con semáforo:

> **🔴 Ancestral — hay que corregir** (2 cosas)
> 1. Faltan **2 stories** que pide la estrategia (solo hay 1).
> 2. El reel del **12** no tiene copy.
>
> **🟢 Goldstone — todo bien.**
>
> **Avisos (no bloquean):**
> - Wanda: el nombre "Wanda Garcia" va con tilde ("García").

---

## Reglas de tono (para ambos modos)
- Semáforo siempre: 🟢 bien / 🔴 hay que corregir. Nada de inglés técnico ("blocker", "warning").
- Separa **"Hay que corregir"** de **"Avisos"**.
- Habla claro y corto, en imperativo ("cambia", "agrega", "confirma").
- Nunca muestres un error en crudo ni un traceback: resume en una frase y propón el siguiente paso.
- Al final, ofrece el siguiente paso natural ("¿lo ajusto?", "¿lo reviso contra la estrategia?").
