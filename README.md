# Tri-Sync

Compara mi historial de **Dixmax/PlayMax**, **Letterboxd** (películas) y **Serializd** (series),
muestra las diferencias en una web local y me deja elegir qué hacer con cada una.

> Uso personal. Las APIs de Dixmax y Serializd son internas (no oficiales) y pueden cambiar.
> Letterboxd se lee desde su export oficial y se escribe con su importador CSV.

## Instalación

Solo hace falta Python 3.10+ (sin dependencias externas).

```bash
git clone https://github.com/AnxoBT/tri-sync.git
cd tri-sync
copy .env.example .env      # y rellénalo
```

### `.env`

| Variable | Qué es |
|---|---|
| `DATA_DIR` | Carpetas donde buscar los exports (zip o carpeta), separadas por `;`. Vacío = Descargas |
| `SERIALIZD_TOKEN` | Cookie `tvproject_credentials` de serializd.com (F12 → Application → Cookies) |
| `SERIALIZD_USER` / `LETTERBOXD_USER` | Tus usuarios |
| `DIXMAX_API_KEY` / `DIXMAX_AUTH_KEY` | API oficial de PlayMax: crea una app en playmax.mx/tusapps.php y autorízala en Panel de Control > Aplicaciones autorizadas |

El `.env`, los exports y las cachés **nunca** se suben al repo (ver `.gitignore`).

## Uso

**Abrir:** doble clic en `Abrir sync.bat` (o `python sync.py`). Se abre la web en http://127.0.0.1:8765.
Para apagarlo, cierra la ventana negra.

1. **Descarga los exports** con los botones de la web (quedan como zip en Descargas, no hace falta descomprimir):
   - **Letterboxd**: cada vez que revises (1 clic).
   - **Dixmax**: opcional; con la API configurada se lee en directo. Descárgalo cuando quieras **fechas exactas**
     (lo detectado solo por la API se registra con la fecha del día de la revisión).
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
