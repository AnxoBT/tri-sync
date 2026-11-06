# Tri-Sync

Compara mi historial de **Dixmax/PlayMax**, **Letterboxd** (películas) y **Serializd** (series),
muestra las diferencias en una web local y me deja elegir qué hacer con cada una.

> Uso personal. Dixmax se usa con su API oficial; la de Serializd es interna (no oficial) y puede cambiar.
> Letterboxd se lee desde su export oficial y se escribe con su importador CSV.

## Instalación (también en otro PC)

1. Instala **Python 3.10+** desde python.org (marca *Add python.exe to PATH*).
2. Descarga la última versión desde **Releases** (zip *Source code*) y descomprímela donde quieras.
   (O `git clone https://github.com/AnxoBT/tri-sync.git`.)
3. Doble clic en **`Abrir Tri-Sync.bat`**. La primera vez instala lo necesario (`tzdata`), crea el acceso directo
   **Tri-Sync** en el escritorio y abre la web. Después ya puedes abrirlo desde el acceso directo.
4. Pestaña **Configuración**: rellena los datos (o copia tu `.env` de otro PC a esta carpeta) → **Probar conexiones**.
5. La primera revisión en un PC nuevo, mejor **Completa** (crea la caché).

Nada personal viaja con el repo: el `.env` (token y claves), la caché y los registros se quedan en cada PC.

### `.env`

| Variable | Qué es |
|---|---|
| `DATA_DIR` | Carpetas donde buscar los exports (zip o carpeta), separadas por `;`. Vacío = Descargas |
| `SERIALIZD_TOKEN` | Cookie `tvproject_credentials` de serializd.com (F12 → Application → Cookies) |
| `SERIALIZD_USER` / `LETTERBOXD_USER` | Tus usuarios |
| `DIXMAX_API_KEY` / `DIXMAX_AUTH_KEY` | API oficial de PlayMax: crea una app en playmax.mx/tusapps.php y autorízala en Panel de Control > Aplicaciones autorizadas |

El `.env`, los exports y las cachés **nunca** se suben al repo (ver `.gitignore`).

## Uso

**Abrir:** doble clic en `Abrir Tri-Sync.bat` (o `python sync.py`). Se abre la web en http://127.0.0.1:8765.
Se abre **sin ventana negra** y **se apaga solo al cerrar la pestaña** (a los ~10 s; si recargas no se apaga).
Si cierras la pestaña en mitad de una revisión o aplicación, termina el trabajo y luego se apaga.
También tienes el botón **⏻ Apagar**. Si lo abres estando ya abierto, solo abre la pestaña.

1. **Descarga los exports** con los botones de la web (quedan como zip en Descargas, no hace falta descomprimir):
   - **Letterboxd**: cada vez que revises (1 clic).
   - **Dixmax**: casi nunca. Con la API configurada se lee en directo, con las fechas exactas de lo nuevo
     (marcas y episodios). Solo hace falta para detectar marcas que **quites** en Dixmax o tras mucho tiempo sin revisar.
2. **Revisión rápida / Completa**: lee directamente el zip (o carpeta) más reciente de cada web en las carpetas de
   `DATA_DIR` (por defecto Descargas; varias separadas por `;`). Busca nombres que empiecen por
   `playmax-userdata-` y `letterboxd-`, ignora los incompletos y compara todo (~2-3 min).
3. Elige qué hacer con cada diferencia → **Simular** → **Aplicar**:
   - Serializd y Dixmax: se cambian directamente.
   - Letterboxd: genera el CSV en `logs/` con botones para abrir la carpeta y el importador.

Todo lo aplicado queda registrado en `logs/ejecucion_*.log`.

### Lo que se hace a mano (la herramienta te da el enlace)

- Borrar entradas o notas, quitar de la watchlist y "me gusta" en Letterboxd (su importador no lo permite).
- Añadir en Dixmax algo que solo está en otra web (hay que buscar la ficha).

## Qué compara

**Películas (Dixmax ↔ Letterboxd)**: vistas, watchlist, notas (Dixmax 0-10 = estrellas × 2),
entradas del diario.

**Series (Dixmax ↔ Serializd)**: episodios vistos con su fecha (con equivalencia a la numeración
actual de TMDB), estado (viendo / watchlist / abandonada / terminada) y nota (redondeo hacia abajo).

## Casos especiales: `rules.json`

Todo lo que no cuadra "por diseño" va aquí y se puede editar:
fichas mal enlazadas en Dixmax, temporadas que TMDB fusionó o reordenó, especiales,
episodios dobles, películas que solo están en una web, etc.

## Estado

- [x] Fase 1: leer las 3 webs, calcular diferencias, web local, guardar plan
- [x] Fase 2: aplicar cambios en Serializd (episodios, estados, notas, terminar serie) y Dixmax (marcar vista, notas)
- [x] Fase 3: generar CSV de importación para Letterboxd (registros con fecha, notas, watchlist)
