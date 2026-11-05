# seriesypelis-sync

Compara mi historial de **Dixmax/PlayMax**, **Letterboxd** (películas) y **Serializd** (series),
muestra las diferencias en una web local y me deja elegir qué hacer con cada una.

> Uso personal. Las APIs de Dixmax y Serializd son internas (no oficiales) y pueden cambiar.
> Letterboxd se lee desde su export oficial y se escribe con su importador CSV.

## Instalación

Solo hace falta Python 3.10+ (sin dependencias externas).

```bash
git clone https://github.com/AnxoBT/seriesypelis-sync.git
cd seriesypelis-sync
copy .env.example .env      # y rellénalo
```

### `.env`

| Variable | Qué es |
|---|---|
| `DATA_DIR` | Carpeta donde dejas los exports de Dixmax y Letterboxd |
| `SERIALIZD_TOKEN` | Cookie `tvproject_credentials` de serializd.com (F12 → Application → Cookies) |
| `SERIALIZD_USER` / `LETTERBOXD_USER` | Tus usuarios |
| `DIXMAX_API_KEY` / `DIXMAX_AUTH_KEY` | API oficial de PlayMax: crea una app en playmax.mx/tusapps.php y autorízala en Panel de Control > Aplicaciones autorizadas |

El `.env`, los exports y las cachés **nunca** se suben al repo (ver `.gitignore`).

## Uso

1. Descarga los exports y descomprímelos en `DATA_DIR`:
   - **Dixmax**: perfil → exportar datos → carpeta `playmax-userdata-*`
   - **Letterboxd**: Settings → Data → Export your data → carpeta `letterboxd-*`
   (se usa siempre el más reciente)
2. Ejecuta:

```bash
python sync.py                  # calcula diferencias y abre la web local
python sync.py --solo series    # o --solo peliculas
python sync.py --sin-calcular   # reabre la web con el último cálculo
```

3. En la web (http://127.0.0.1:8765) eliges para cada diferencia qué hacer y pulsas:
   - **Simular**: te dice qué haría, sin tocar nada.
   - **Aplicar**: lo hace de verdad (pide confirmación).
     - Serializd y Dixmax: se cambian directamente con tu sesión.
     - Letterboxd: genera el CSV en `logs/` con botones para abrir la carpeta y el importador
       (registros/notas → `letterboxd.com/import/`; watchlist → tu watchlist > Import).
   - **Guardar plan**: guarda lo elegido en `logs/` sin ejecutar.

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
