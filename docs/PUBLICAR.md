# Publicar Aura en el directorio comunitario de Claude

Guía para convertir Aura de "herramienta del equipo" en un plugin que cualquiera pueda instalar
desde el directorio comunitario de Anthropic.

**Estado actual:** Aura ya es instalable por cualquiera con el enlace del repositorio. Publicar en
el directorio **no añade capacidad**: añade descubrimiento, y con él usuarios desconocidos. Todo
lo que sigue existe para que esos usuarios no se lleven una mala experiencia.

Las fuentes oficiales están citadas; donde la documentación no dice nada, se indica
explícitamente para no confundir requisito con costumbre.

---

## Fase 0 — Antes de tocar código

Tres condiciones que no son técnicas. Si alguna falla, no publiques todavía.

- [ ] **La calibración está hecha** y la revisora confía en el criterio (guía de marca real y
      varios videos comparados con lo que ella marcó a mano).
- [ ] **Uno o dos meses de uso real** sin sobresaltos.
- [ ] **Quieres usuarios.** Publicado, los problemas de desconocidos son trabajo tuyo: gente en
      Macs Intel, sin ffmpeg, esperando que funcione en Windows. Si la respuesta es "estaría bien
      tenerlos" y no "los quiero", espera.

---

## Fase 1 — Lo que hay que cambiar en Aura

Estos son los huecos concretos de **este** plugin, no una lista genérica.

### 1.1 Idioma
- [ ] `plugin.json`: `description` en inglés (es lo que se ve en el directorio).
- [ ] `README.md` del plugin en inglés, con los requisitos **arriba del todo**.
- [ ] Decidir las skills: inglés, o bilingüe con el idioma detectado del usuario. Mantener solo
      español limita el público a equipos hispanohablantes — que es una decisión válida, pero
      hay que tomarla a conciencia.

### 1.2 No dar por supuesto el flujo de un equipo concreto
- [ ] Quitar la suposición de **Google Drive**: hablar de "carpeta de trabajo" y dejar Drive como
      un ejemplo. (El motor ya soporta varias carpetas desde `v0.4.0`.)
- [ ] Quitar la suposición del flujo editora → junior → revisora del texto de las skills.
- [ ] El Sheet debe ser claramente opcional y estar apagado por defecto.

### 1.3 Requisitos visibles antes de instalar
Que nadie descubra estas cosas a mitad de la instalación:
- [ ] **Solo macOS con chip Apple** (el motor usa Apple Vision, NSSpellChecker y MLX).
- [ ] **Descarga ~1,5 GB** del modelo de voz en la primera revisión.
- [ ] **Consume la cuota de Claude del usuario**: cada video son ~15 imágenes y una respuesta
      larga. Conviene dar una cifra orientativa por video.
- [ ] Necesita **Homebrew, uv y ffmpeg**; el plugin los instala si faltan.

### 1.4 Reducir lo que el plugin hace sin preguntar ← lo más importante
Hoy `/aura:instalar` hace cosas fuertes en la máquina de quien lo ejecute: instala Homebrew con
`curl | bash`, instala paquetes con `brew`, clona un repositorio en `~/videoqa` y **edita
`~/.claude/settings.json`** para añadir permisos. Con tu esposa eso es razonable porque tú
respondes por ello; con un desconocido es mucho.

- [ ] Pedir confirmación explícita **antes de cada acción de instalación**, no solo al principio.
- [ ] Explicar en el README exactamente qué toca y dónde.
- [ ] Considerar no editar `settings.json` por defecto y dejarlo como una pregunta aparte.
- [ ] Revisar el hook de `SessionStart`: se ejecuta un script en cada sesión. Es correcto que
      exista, pero conviene documentarlo y que siga siendo de solo lectura y rápido.

La documentación de Anthropic advierte que **los plugins ejecutan código con los privilegios del
usuario** y que las hooks corren con ese mismo nivel de confianza
([discover-plugins](https://code.claude.com/docs/en/discover-plugins.md)); las candidaturas al
directorio comunitario pasan por **validación automática y un filtro de seguridad**, así que
cuanto menos agresiva sea la instalación, mejor.

---

## Fase 2 — Lista técnica

### 2.1 Manifiesto
Lo único **documentado como obligatorio** es `name`, en kebab-case. Documentados como opcionales:
`displayName`, `version`, `description`, `author` (`name`, `email`, `url`), `dependencies`
([plugins-reference](https://code.claude.com/docs/en/plugins-reference.md)).

> La documentación **no lista** `homepage`, `license` ni `keywords` como campos del esquema. Los
> nuestros los llevan y `validate` no protesta, pero no cuentes con que se muestren en el
> directorio.

- [ ] `name`, `version` (semver) y una `description` que se entienda sin contexto.
- [ ] `author` con nombre y una URL de contacto.

### 2.2 Validación
- [ ] `claude plugin validate plugins/aura --strict` sin avisos.
- [ ] `claude plugin validate . --strict` (el catálogo).
- [ ] Instalar desde cero en una cuenta de usuario limpia de tu Mac y recorrer el flujo entero.
- [ ] Opcional pero recomendable: `claude plugin eval` para medir que las skills se disparan
      cuando deben ([plugin-evals](https://code.claude.com/docs/en/plugin-evals.md)). No está
      documentado como requisito para publicar.

### 2.3 Skills
- [ ] `description` clara y con disparadores explícitos (límite de 1.536 caracteres contando el
      "cuándo usarla"; nosotros usamos menos de 200, que se lee mejor).
- [ ] `disable-model-invocation: true` en todo lo que tenga efectos — ya lo cumplimos en
      `instalar`, `ajustar`, `activar-automatico` y `actualizar`.
- [ ] `allowed-tools` lo más estrecho posible: es lo que evita que Claude pida permiso a cada
      paso, así que pedir de más se nota.
- [ ] Ningún secreto ni ruta personal dentro de las skills.

### 2.4 Documentación y licencia
- [ ] README con instalación y uso (recomendado por la documentación, no listado como requisito).
- [ ] LICENSE: la documentación **no dice nada**. Nosotros ya tenemos MIT; déjalo.
- [ ] Un CHANGELOG corto ayuda a que la gente entienda qué cambia al actualizar.

### 2.5 Versiones
- [ ] Semver en `plugin.json` **y** en la entrada del catálogo: los usuarios reciben la
      actualización cuando subes ese número
      ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces.md)).
- [ ] No reutilizar un número ya publicado.

---

## Fase 3 — El envío

1. Repasa que todo lo anterior esté hecho.
2. Envía por el formulario oficial: [clau.de/plugin-directory-submission](https://clau.de/plugin-directory-submission)
   (también desde claude.ai → Ajustes → Directorio, o desde la Consola).
3. **No abras un pull request** contra `anthropics/claude-plugins-community`: se cierran
   automáticamente.
4. Pasa validación automática y filtro de seguridad, y luego revisión para aprobación. Los
   aprobados se fijan a un commit concreto y se sincronizan al catálogo.

Dos cosas que conviene tener claras:
- El directorio **comunitario** no es el **oficial** (`claude-plugins-official`), que es curado
  por Anthropic a su criterio. No se solicita.
- No prometas ni des a entender ningún sello de "verificado por Anthropic".

---

## Fase 4 — Después de publicar

- [ ] Decide y **escribe en el README** si das soporte o si se ofrece tal cual.
- [ ] Activa las Issues del repositorio, o desactívalas a conciencia con una nota que explique
      dónde reportar.
- [ ] Ten un plan para lo que ya sabemos que falla en manos ajenas: Macs Intel, `winget`/ffmpeg
      ausentes, la sesión de Claude que caduca, y la cuota.
- [ ] Al publicar una versión nueva, sube el número en los dos sitios y prueba la actualización
      con `claude plugin update aura` antes de anunciarla.

---

## Atajo: probar con gente sin publicar

Mándales el enlace del repositorio y que añadan el catálogo con
**Agregar ▾ → Agregar desde un repositorio → `hongs05/videoqa`**. Consigues usuarios reales y
feedback sin comprometerte a mantener nada, y puedes parar cuando quieras. Es el paso previo
sensato antes de la Fase 3.
