<p align="center">
  <img src="docs/icon.png" width="112" alt="Tri-Sync">
</p>

<h1 align="center">Tri-Sync</h1>

<p align="center">
  <a href="https://github.com/AnxoBT/tri-sync/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/AnxoBT/tri-sync?style=flat-square&color=3FB0FF"></a>
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%2B-0078D4?style=flat-square&logo=windows&logoColor=white">
  <img alt="Android 8.0+" src="https://img.shields.io/badge/Android-8.0%2B-34A853?style=flat-square&logo=android&logoColor=white">
  <img alt="iPhone (test)" src="https://img.shields.io/badge/iPhone-test-555555?style=flat-square&logo=apple&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white">
</p>

<br>

<details open>
<summary><b>English</b></summary>

<br>

<p align="center">Keep your watch history in sync between Dixmax, Letterboxd, Serializd and AniList.</p>

<p align="center"><a href="https://github.com/AnxoBT/tri-sync/releases/latest"><b>Download</b></a> · Windows (Python) · Android APK · iPhone IPA (test)</p>

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🔍 Review</h3>
      Compares what you watched on Dixmax with your other apps and lists everything that doesn't match: films, episodes with their dates, ratings, statuses and favourites.
    </td>
    <td width="33%" valign="top">
      <h3>✅ Fix in one click</h3>
      Choose what to do with each difference, simulate it, apply it. Dixmax, Serializd and AniList change directly; Letterboxd too with its API, or through its CSV importer.
    </td>
    <td width="33%" valign="top">
      <h3>📊 Statistics</h3>
      Your films, series and anime in numbers: world map, your year, streaks and marathons, people, studios, budgets, hidden gems and curiosities.
    </td>
  </tr>
</table>

### Features

**Apps: connect only the ones you use**

- **Dixmax / PlayMax** is the centre: everything is compared with it, so it is the only one required.
  With its official API you don't even need its export
- **Letterboxd** (films), **Serializd** (series) and **AniList** (anime) are optional; the ones you
  don't connect don't show up anywhere and are not reviewed
- The first time, a short **welcome guide** (4 steps) explains how it works, and a welcome screen takes you to
  **Settings → Your apps**, with a card per app explaining what it does and how to connect it
- **English and Spanish**: it follows your device's language, and you can change it in Settings. Everything is
  translated (reviews, statistics, curiosities); only your film and series titles keep the names they have on Dixmax

**Review**

- Quick (5-15 s, only what's new) or full (from scratch)
- Films (Dixmax ↔ Letterboxd): watched, watchlist, ratings (Dixmax 0-10 = stars × 2), diary entries
- Series (Dixmax ↔ Serializd): watched episodes with their real date (mapped to TMDB's current
  numbering), status (watching / watchlist / dropped / finished) and rating
- Anime (Dixmax → AniList, and AniList ↔ Serializd): status, episodes, rating, start/end dates and
  favourites. AniList splits seasons into separate entries; they are matched with
  [Fribb/anime-lists](https://github.com/Fribb/anime-lists)
- Each series has a single status in Serializd, the one it has in Dixmax
- Group actions, search, collapsible sections; what you apply disappears from the list
- Special cases (badly linked records, merged seasons, specials…) go in your own `rules.json`

**Apply**

- **Simulate** first, then **Apply**, with progress and cancel
- Dixmax, Serializd and AniList: changed directly through their APIs, keeping the real dates
- Letterboxd: with its official API (optional) it changes directly (diary with date, rating and ♥,
  ratings, watchlist). Without it, a CSV for its importer is created
- Everything applied is logged, and shows up in **History**

**Statistics**

- Everything / Films / Series / Anime, with the same 16 curiosities per section
- World map by main production country (tap a country to see its titles), filtered by status
- Your year, when you watch (day and hour), marathons and streaks (also with one series), your most
  intense month
- People (directors, full cast with credited guests, Japanese voice actors), studios, networks,
  franchises, genres, decades
- Popularity against everyone (IMDb, TVmaze, AniList): hidden gems, most popular, what you liked
  more or less than people
- Budgets and worldwide box office: the most expensive, best deals and flops
- Batch marks (many episodes in the same minute) are spread realistically; `rules.json` lets you
  mark which ones were real

**History**

- Every review and every application; tap a row to see what changed since the previous one

### Platforms

**Windows (and any PC with Python)**: the app is a small local web server; it opens in your browser
and closes by itself when you close the tab.

**Android**: the same app inside an APK (Python included with Chaquopy). It works on its own, without
the PC.

- **📱 Send to phone** (on the PC, Settings): over the USB cable (adb), installs or updates the app and
  copies your settings, cache and latest exports. Nothing goes over the internet
- **Import export…**: Android doesn't let apps read Downloads, so you pick the zip
- Swipe sideways to change tab; the screen stays on while it reviews or applies

**iPhone (test)**: the same app (Python included with BeeWare Briefcase). External links open in
Safari, Letterboxd CSVs go to the share sheet, and AniList and Letterboxd connect inside the app. The
IPA is unsigned: install it with Sideloadly or AltStore (with a free Apple ID it has to be reinstalled
every 7 days). It is built and tried in the iOS simulator by GitHub Actions, not yet on a real iPhone.

### Install

From the [latest release](https://github.com/AnxoBT/tri-sync/releases/latest):

- **Windows**: install **Python 3.10+** from python.org (tick *Add python.exe to PATH*), download the
  *Source code* zip, unzip it and double-click **`Abrir Tri-Sync.bat`**. The first time it installs what
  it needs (`tzdata`), creates a **Tri-Sync** shortcut on the desktop and opens the web page.
- **Android**: `Tri-Sync-vX.Y.Z.apk`; open it on your phone (Android 8.0 or later; allow installing from
  unknown sources when asked). Or use **Send to phone** from the PC.
- **iPhone (test)**: `Tri-Sync-X.Y.Z-iOS.ipa`, unsigned; install it with Sideloadly or AltStore.

**Updates**: a green bar tells you when there is a new release. On the PC it downloads and installs it
(keeping a copy of the current version) and restarts; on Android it downloads the APK and opens the
installer; on iPhone, install the new IPA.

### Connecting your apps

| App | What you need |
|---|---|
| Dixmax | `apiKey` (playmax.mx/tusapps.php → Add App) and `authKey` (Control Panel → Authorised apps). Optional: its export, only to detect marks you *remove* |
| Letterboxd | Your username, and its export each time you review (Settings → Data on letterboxd.com). Optional: its API (`client_id`/`client_secret`, requested at letterboxd.com/api-beta; redirect `http://127.0.0.1:8765/letterboxd`) |
| Serializd | Your username and the `tvproject_credentials` cookie of serializd.com (F12 → Application → Cookies). It expires now and then |
| AniList | **Connect with AniList** and *Authorize* (lasts a year). Only your anime list is touched |

All of it is stored in `.env`, next to the app (or in the app's private folder on the phone).

### Compatibility

| Platform | Device | Status |
|---|---|---|
| Windows | Windows 11, Python 3.14 | Used daily |
| Android | vivo V2337, Android 15 | Tested |
| Android | Other brands | Not tested yet |
| iPhone | iOS simulator (GitHub Actions) | Simulator only |

On the phone the app only works with the screen on: Android and iOS pause it in the background.

### Privacy and security

- Nothing is sent anywhere except to the apps you connect (and to public sources of film and series
  data: Radarr's metadata, Wikidata, TVmaze, AniList). No accounts, no analytics
- Your keys and tokens stay in your `.env`, which is never uploaded (see `.gitignore`); the web page only
  shows whether a secret is set, never its value
- The server only listens on `127.0.0.1`, and rejects requests from other websites open in your browser
  (cross-site requests and DNS rebinding)
- Your `rules.json`, cache, logs and exports are personal and are not in the repository

### Build and test

```sh
python -m unittest discover -s tests -v     # tests (no network, temporary folder)
python sync.py                               # run it on the PC
cd android && ./gradlew assembleRelease      # Android APK (JDK 17 + Android SDK; android/local.properties with sdk.dir)
python -m tools.generar_icono_android        # Android and iPhone icons from web/logo.ico
```

iPhone (on a Mac; GitHub Actions does it on every change in `ios/` with `.github/workflows/ios.yml`):

```sh
pip install briefcase
briefcase create iOS && briefcase build iOS && briefcase run iOS
```

The APK is signed with its own key (`~/.android/trisync-release.jks`, details in
`android/keystore.properties`, neither in the repository): **keep it**, with another key the phone won't
install the update over the old version.

### How it works

- `core/`: reading each app (Dixmax API and export, Letterboxd export, Serializd's internal API, AniList
  GraphQL), the differences (`diff.py`), applying them (`apply.py`) and the statistics
  (`estadisticas.py`, `metadatos.py`)
- `web/`: the local server (`server.py`, standard library only) and the page (`index.html`, one file)
- `android/` and `ios/`: the same Python code inside an app, showing the page in a web view
- Serializd's API is internal (not official) and may change; Letterboxd's official API is by request

### License

Copyright © 2026 AnxoBT. Licensed under the [GNU General Public License v3.0](LICENSE): you can
use, study, share and modify it, but anything you distribute that is based on this code must be
released under the same licence, with its source code.

</details>

<details>
<summary><b>Español</b></summary>

<br>

<p align="center">Mantén tu historial sincronizado entre Dixmax, Letterboxd, Serializd y AniList.</p>

<p align="center"><a href="https://github.com/AnxoBT/tri-sync/releases/latest"><b>Descargar</b></a> · Windows (Python) · APK de Android · IPA de iPhone (prueba)</p>

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🔍 Revisión</h3>
      Compara lo que has visto en Dixmax con tus otras apps y te enseña todo lo que no cuadra: películas, episodios con su fecha, notas, estados y favoritas.
    </td>
    <td width="33%" valign="top">
      <h3>✅ Arreglar con un clic</h3>
      Eliges qué hacer con cada diferencia, lo simulas y lo aplicas. Dixmax, Serializd y AniList cambian directamente; Letterboxd también con su API, o con su importador CSV.
    </td>
    <td width="33%" valign="top">
      <h3>📊 Estadísticas</h3>
      Tus películas, series y anime en números: mapa del mundo, tu año, rachas y maratones, personas, estudios, presupuestos, joyas ocultas y curiosidades.
    </td>
  </tr>
</table>

### Funciones

**Apps: conecta solo las que uses**

- **Dixmax / PlayMax** es el centro: todo se compara con él, así que es la única imprescindible. Con su
  API oficial ni siquiera hace falta su export
- **Letterboxd** (películas), **Serializd** (series) y **AniList** (anime) son opcionales; las que no
  conectes no aparecen en ningún sitio ni se revisan
- La primera vez, una **guía de bienvenida** de 4 pasos explica cómo funciona, y una bienvenida te lleva a
  **Configuración → Tus aplicaciones**, con una tarjeta por app que explica qué hace y cómo conectarla
- **Español e inglés**: sigue el idioma del dispositivo y se cambia en Configuración. Se traduce todo (revisión,
  estadísticas, curiosidades); solo los títulos de tus películas y series se quedan como los tiene Dixmax

**Revisión**

- Rápida (5-15 s, solo lo nuevo) o completa (desde cero)
- Películas (Dixmax ↔ Letterboxd): vistas, watchlist, notas (Dixmax 0-10 = estrellas × 2), entradas del diario
- Series (Dixmax ↔ Serializd): episodios vistos con su fecha real (con la numeración actual de TMDB),
  estado (viendo / pendiente / abandonada / terminada) y nota
- Anime (Dixmax → AniList, y AniList ↔ Serializd): estado, episodios, nota, fechas de inicio/fin y
  favoritos. AniList separa las temporadas; se cruzan con [Fribb/anime-lists](https://github.com/Fribb/anime-lists)
- Cada serie tiene un solo estado en Serializd, el que tiene en Dixmax
- Acciones por grupo, búsqueda, secciones plegables; lo que aplicas desaparece de la lista
- Los casos especiales (fichas mal enlazadas, temporadas fusionadas, especiales…) van en tu `rules.json`

**Aplicar**

- Primero **Simular** y luego **Aplicar**, con progreso y botón de cancelar
- Dixmax, Serializd y AniList: se cambian directamente por sus APIs, con las fechas reales
- Letterboxd: con su API oficial (opcional) se cambia directamente (diario con fecha, nota y ♥, notas,
  watchlist). Sin ella, se genera un CSV para su importador
- Todo lo aplicado queda registrado y sale en **Historial**

**Estadísticas**

- Todo / Películas / Series / Anime, con las mismas 16 curiosidades por sección
- Mapa del mundo por país principal de producción (toca un país para ver sus títulos), por estado
- Tu año, cuándo ves (día y hora), maratones y rachas (también con una misma serie), tu mes más intenso
- Personas (directores, reparto completo con invitados acreditados, voces japonesas), estudios,
  cadenas, sagas, géneros, décadas
- Popularidad frente a la gente (IMDb, TVmaze, AniList): joyas ocultas, lo más popular, lo que te
  gustó más o menos que a los demás
- Presupuestos y taquilla mundial: las más caras, los mejores negocios y los fracasos
- Las marcas en tanda (muchos episodios en el mismo minuto) se reparten de forma realista; en
  `rules.json` puedes decir cuáles fueron de verdad

**Historial**

- Cada revisión y cada aplicación; toca una fila para ver qué ha cambiado desde la anterior

### Plataformas

**Windows (y cualquier PC con Python)**: la app es un pequeño servidor web local; se abre en el navegador
y se cierra sola al cerrar la pestaña.

**Android**: la misma app dentro de un APK (con Python, gracias a Chaquopy). Funciona sola, sin el PC.

- **📱 Pasar al móvil** (en el PC, Configuración): por el cable USB (adb), instala o actualiza la app y le
  pasa tu configuración, la caché y los últimos exports. Nada pasa por internet
- **Importar export…**: Android no deja a las apps leer Descargas, así que eliges el zip
- Desliza a un lado para cambiar de pestaña; la pantalla no se apaga mientras revisa o aplica

**iPhone (prueba)**: la misma app (con Python, gracias a BeeWare Briefcase). Los enlaces de fuera se
abren en Safari, los CSV de Letterboxd van al menú de compartir, y AniList y Letterboxd se conectan
dentro de la app. El IPA no está firmado: instálalo con Sideloadly o AltStore (con un Apple ID gratuito
hay que reinstalarlo cada 7 días). Lo compila y lo prueba en el simulador GitHub Actions; aún no se ha
probado en un iPhone de verdad.

### Instalar

Desde la [última release](https://github.com/AnxoBT/tri-sync/releases/latest):

- **Windows**: instala **Python 3.10+** desde python.org (marca *Add python.exe to PATH*), descarga el zip
  *Source code*, descomprímelo y haz doble clic en **`Abrir Tri-Sync.bat`**. La primera vez instala lo
  necesario (`tzdata`), crea el acceso directo **Tri-Sync** en el escritorio y abre la web.
- **Android**: `Tri-Sync-vX.Y.Z.apk`; ábrelo en el móvil (Android 8.0 o superior; permite instalar de
  orígenes desconocidos cuando lo pida). O usa **Pasar al móvil** desde el PC.
- **iPhone (prueba)**: `Tri-Sync-X.Y.Z-iOS.ipa`, sin firmar; instálalo con Sideloadly o AltStore.

**Actualizar**: una barra verde avisa cuando hay una release nueva. En el PC la descarga, la instala
(guardando una copia de la versión actual) y se reinicia; en Android descarga el APK y abre el
instalador; en el iPhone, instala el IPA nuevo.

### Conectar tus apps

| App | Qué necesitas |
|---|---|
| Dixmax | `apiKey` (playmax.mx/tusapps.php → Añadir App) y `authKey` (Panel de Control → Aplicaciones autorizadas). Opcional: su export, solo para detectar marcas que *quites* |
| Letterboxd | Tu usuario, y su export cada vez que revises (Settings → Data en letterboxd.com). Opcional: su API (`client_id`/`client_secret`, se pide en letterboxd.com/api-beta; dirección de vuelta `http://127.0.0.1:8765/letterboxd`) |
| Serializd | Tu usuario y la cookie `tvproject_credentials` de serializd.com (F12 → Application → Cookies). Caduca de vez en cuando |
| AniList | **Conectar con AniList** y *Authorize* (dura un año). Solo se toca tu lista de anime |

Todo se guarda en `.env`, junto a la app (o en la carpeta privada de la app en el móvil).

### Compatibilidad

| Plataforma | Dispositivo | Estado |
|---|---|---|
| Windows | Windows 11, Python 3.14 | Uso diario |
| Android | vivo V2337, Android 15 | Probado |
| Android | Otras marcas | Sin probar aún |
| iPhone | Simulador de iOS (GitHub Actions) | Solo simulador |

En el móvil la app solo trabaja con la pantalla encendida: Android e iOS la pausan en segundo plano.

### Privacidad y seguridad

- No se manda nada a ningún sitio salvo a las apps que conectes (y a fuentes públicas de datos de
  películas y series: los metadatos de Radarr, Wikidata, TVmaze, AniList). Sin cuentas ni analíticas
- Tus claves y tokens se quedan en tu `.env`, que nunca se sube (ver `.gitignore`); la web solo dice si
  un secreto está puesto, nunca su valor
- El servidor solo escucha en `127.0.0.1` y rechaza peticiones de otras webs abiertas en el navegador
  (peticiones cruzadas y DNS rebinding)
- Tu `rules.json`, la caché, los registros y los exports son personales y no están en el repositorio

### Compilar y probar

```sh
python -m unittest discover -s tests -v     # pruebas (sin red, en una carpeta temporal)
python sync.py                               # abrirlo en el PC
cd android && ./gradlew assembleRelease      # APK de Android (JDK 17 + Android SDK; android/local.properties con sdk.dir)
python -m tools.generar_icono_android        # iconos de Android y de iPhone a partir de web/logo.ico
```

iPhone (en un Mac; GitHub Actions lo hace en cada cambio de `ios/` con `.github/workflows/ios.yml`):

```sh
pip install briefcase
briefcase create iOS && briefcase build iOS && briefcase run iOS
```

El APK se firma con una clave propia (`~/.android/trisync-release.jks`, datos en
`android/keystore.properties`, ninguno de los dos en el repositorio): **consérvala**, con otra clave el
móvil no instala la actualización encima de la versión anterior.

### Cómo funciona

- `core/`: lectura de cada app (API y export de Dixmax, export de Letterboxd, API interna de Serializd,
  GraphQL de AniList), las diferencias (`diff.py`), aplicarlas (`apply.py`) y las estadísticas
  (`estadisticas.py`, `metadatos.py`)
- `web/`: el servidor local (`server.py`, solo librería estándar) y la página (`index.html`, un solo archivo)
- `android/` e `ios/`: el mismo código Python dentro de una app, que enseña la página en una vista web
- La API de Serializd es interna (no oficial) y puede cambiar; la oficial de Letterboxd se concede bajo petición

### Licencia

Copyright © 2026 AnxoBT. Con licencia [GNU General Public License v3.0](LICENSE): puedes usarla,
estudiarla, compartirla y modificarla, pero lo que distribuyas basado en este código tiene que
publicarse con la misma licencia y con su código fuente.

</details>
