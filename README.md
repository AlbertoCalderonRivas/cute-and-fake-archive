# CUTE & FAKE

Web estática que se genera sola a partir de una carpeta de Google Drive.

```
Drive (carpeta media) ──Apps Script cada 5 min──▶ GitHub Actions ──▶ GitHub Pages
                       (detecta cambios)          rclone + build.py
        ▲                                               │
        └────────────── _ESTADO.txt ◀───────────────────┘
```

## Archivos

| Archivo | Qué es |
|---|---|
| `config.json` | Título, ID de la carpeta de Drive y ajustes de conversión. **Sin credenciales.** |
| `build.py` | Lee `media/`, convierte fotos y vídeos, escribe `site/contenido.json` y `ESTADO.txt`. |
| `web/` | La interfaz (HTML, CSS, JS y fuente). `build.py` la copia a `site/`. |
| `.github/workflows/publicar.yml` | Descarga Drive, genera y publica. |
| `apps-script/vigilante.gs` | Vigila Drive y lanza el workflow. |
| `LEEME_para_editores.txt` | Instrucciones para quien sube contenido. |
| `herramientas/generar_ejemplo.py` | Crea una carpeta `ejemplo_media/` con todos los casos para probar. |

## Probar en local

```bash
pip install -r requirements.txt          # y tener ffmpeg instalado
python herramientas/generar_ejemplo.py   # opcional: contenido de prueba
python build.py --media ejemplo_media
python -m http.server -d site 8000       # abrir http://localhost:8000
```

Las conversiones se guardan en `.cache/`: un archivo que no ha cambiado no se vuelve a procesar.

## Puesta en marcha (una vez)

**1. Cuenta de servicio de Google** (el "usuario robot" que lee Drive)
1. [console.cloud.google.com](https://console.cloud.google.com) → crea un proyecto → *APIs y servicios* → activa **Google Drive API**.
2. *Credenciales* → *Crear credenciales* → **Cuenta de servicio** → créala → pestaña *Claves* → *Agregar clave* → JSON. Se descarga un archivo.
3. Copia el email de la cuenta de servicio (`algo@proyecto.iam.gserviceaccount.com`) y **comparte con él la carpeta media como Editor** (Editor para que pueda sobrescribir `_ESTADO.txt`).

> Si la carpeta está en una **unidad compartida**, añade en el workflow la variable `RCLONE_CONFIG_DRIVE_TEAM_DRIVE` con el ID de esa unidad.

**2. GitHub**
1. Sube este repositorio (sin `media/`, `site/` ni el JSON de la clave).
2. *Settings → Secrets and variables → Actions* → nuevo secret `GDRIVE_SERVICE_ACCOUNT` con **todo el contenido** del JSON descargado. Después borra ese archivo de tu ordenador o guárdalo en un sitio seguro.
3. *Settings → Pages* → *Source*: **GitHub Actions**.
4. Pon el ID de la carpeta en `config.json` → `drive.carpeta_id`.
5. Crea un token: *Settings (de tu cuenta) → Developer settings → Fine-grained tokens* → solo este repositorio → permiso **Contents: Read and write**.

**3. Apps Script** — sigue las instrucciones de la cabecera de `apps-script/vigilante.gs` (propiedades `CARPETA_ID`, `GITHUB_REPO`, `GITHUB_TOKEN` y ejecutar `instalar`).

Comprobación: *Actions → Publicar web → Run workflow*. Al terminar debe aparecer `_ESTADO.txt` en la carpeta de Drive.

## Ajustar la portada

En `config.json` → `portada` hay dos juegos de valores: `movil` (pantallas de menos de `limite_movil_px`) y `escritorio`.

| Clave | Qué controla |
|---|---|
| `iconos_por_pantalla` / `fondos_por_pantalla` | Cuántos se ven a la vez, de media. 1 = uno por pantalla. |
| `iconos_tamano` / `fondos_tamano` | `[mínimo, máximo]`. 1 = ocupa toda la pantalla, 0.3 = un tercio. Cada elemento coge un tamaño al azar dentro del rango. |
| `hueco` | Espacio mínimo entre dos elementos de la misma capa, en pantallas (0.1 = una décima de pantalla). |
| `semilla` (fuera de `portada`) | Cambia la distribución aleatoria. |

Para probar valores en directo, abre la web con `?ajustes` al final de la dirección (`https://…/?ajustes`). Sale un panel con deslizadores y un botón que copia el bloque listo para pegar en `config.json`. En el móvil se ajustan los valores de móvil; en el PC, los de escritorio. Para ajustar los de móvil desde el PC, estrecha la ventana.

## Reglas del contenido

- Cada carpeta de primer nivel = un post. `01 Nombre` → se ordena por el número y se muestra «Nombre». Sin número va al final, por orden alfabético.
- `_algo` y `.algo` no se publican. `_fondo/` = capturas del fondo de la portada.
- Icono = archivo llamado `icono` (gif/png/jpg/webp/mp4/mov…). Si no hay, la primera imagen o vídeo (orden alfabético), buscando también en subcarpetas.
- Tipo de post:
  - **enlace**: aparte del icono, solo hay un documento o un acceso directo con una URL → el clic abre la URL.
  - **media**: solo hay una imagen o un vídeo y no hay icono (o solo hay icono) → se ve en la portada, sin clic. Los vídeos van en bucle y en silencio.
  - **carpeta**: todo lo demás → página propia con la cuadrícula.
- Una sola subcarpeta se aplana. Varias subcarpetas → tarjetas con título, cada una con su página (`#/post/subcarpeta`).
- En la cuadrícula: imagen (clic = ampliar), vídeo con controles, texto con scroll, PDF (miniatura de la primera página, abre en otra pestaña), enlace (icono + dominio, abre en otra pestaña).
- Los nombres de archivo nunca se muestran.

### Formatos

| Entrada | Qué se hace |
|---|---|
| jpg, png, webp, heic, tif… | Gira según EXIF, reduce a 2000 px como máximo. Con transparencia → png, sin ella → jpg. |
| gif | Tal cual (para no romper la animación ni la transparencia). |
| mp4/mov H.264 ≤ 15 MB | Solo se reorganiza para que empiece a reproducirse antes (`faststart`). |
| Otros vídeos | Se recomprimen a H.264, 1280 px como máximo. |
| Vídeos (todos) | Se saca el primer fotograma como póster: se ve al instante mientras carga. |
| Google Docs / docx / txt / md | Se convierten a texto con formato básico. Si solo hay una URL, son un enlace. |
| .url / .webloc | Enlace (los accesos directos que se crean al arrastrar un link del navegador). |

**Transparencia:** solo GIF y PNG la tienen. Un MP4 nunca es transparente.

## Límites de GitHub Pages

Unos 1 GB por web y 100 GB de tráfico al mes (límite blando). Con unas decenas de vídeos de 1–3 MB hay mucho margen. Si algún día se queda corto, el último paso del workflow se puede cambiar por Cloudflare Pages sin tocar nada más.
