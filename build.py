#!/usr/bin/env python3
"""
Convierte la carpeta `media` (copia de Drive) en la web estática.

    python build.py                       # usa ./media y genera ./site
    python build.py --media ejemplo_media # para probar con el ejemplo

Resultado:
    site/                 web lista para publicar (web/ + contenido.json + m/)
    ESTADO.txt            informe para los editores (se sube a Drive como _ESTADO.txt)
    .cache/               conversiones ya hechas (no se repiten si el archivo no cambia)

Reglas (resumen; detalle en README.md):
  - Cada carpeta de primer nivel es un post. "01 Nombre" -> orden 1, título "Nombre".
  - Lo que empieza por "_" o "." no se publica. "_fondo" contiene las capturas del fondo.
  - Un archivo llamado "icono" (imagen o vídeo) es el icono y no se muestra como contenido.
    Si no hay, se usa la primera imagen o vídeo que se encuentre.
  - Tipo de post:
      * enlace -> solo hay un doc/archivo con una URL      (clic = abre la URL)
      * media  -> solo hay una imagen o vídeo, sin icono   (sin clic)
      * carpeta-> cualquier otra cosa                      (clic = página con cuadrícula)
    Una única subcarpeta se "aplana" (su contenido se muestra directamente).
    Varias subcarpetas se muestran como tarjetas, cada una con su propia página.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import plistlib
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps

try:  # fotos de iPhone
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC = True
except ImportError:
    HEIC = False

VERSION_CACHE = "3"  # cambiar para forzar que se regenere todo

EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".avif", ".bmp", ".tif", ".tiff"}
EXT_VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv", ".3gp"}
EXT_TEXTO = {".txt", ".md", ".docx"}
EXT_ENLACE = {".url", ".webloc"}
EXT_PDF = {".pdf"}
IGNORADOS = {".ds_store", "thumbs.db", "desktop.ini", "icon\r"}
NOMBRE_ICONO = "icono"

RE_URL = re.compile(r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+)", re.I)
RE_PREFIJO = re.compile(r"^\s*(\d+)\s*[-_.)]?\s*")


# --------------------------------------------------------------------------- informe
class Informe:
    def __init__(self):
        self.avisos: list[str] = []
        self.errores: list[str] = []

    def aviso(self, ruta: str, msg: str):
        self.avisos.append(f"⚠️  «{ruta}»: {msg}")

    def error(self, ruta: str, msg: str):
        self.errores.append(f"❌ «{ruta}»: {msg}")

    def texto(self, n_posts: int, zona: str) -> str:
        ahora = dt.datetime.now(ZoneInfo(zona)).strftime("%d/%m/%Y a las %H:%M")
        lineas = [f"✅ Web actualizada el {ahora}", f"{n_posts} posts publicados.", ""]
        if self.errores or self.avisos:
            lineas.append("Cosas a revisar (lo demás se ha publicado bien):")
            lineas += self.errores + self.avisos
        else:
            lineas.append("Todo correcto, sin avisos.")
        lineas += ["", "Este archivo lo escribe el sistema automáticamente. No hace falta tocarlo."]
        return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------- utilidades
def oculto(p: Path) -> bool:
    return p.name.startswith(("_", ".")) or p.name.lower() in IGNORADOS


def clave_orden(p: Path):
    """Primero los que llevan número delante (por número), luego el resto alfabético."""
    m = RE_PREFIJO.match(p.name)
    if m and m.end() < len(p.name):
        return (0, int(m.group(1)), p.name.casefold())
    return (1, 0, p.name.casefold())


def titulo(nombre: str) -> str:
    t = RE_PREFIJO.sub("", nombre, count=1).strip()
    return t or nombre


def slugify(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t or "post"


def unico(slug: str, usados: set) -> str:
    s, n = slug, 2
    while s in usados:
        s, n = f"{slug}-{n}", n + 1
    usados.add(s)
    return s


def normalizar_url(u: str) -> str:
    u = u.strip().rstrip(".,;)")
    return u if u.lower().startswith(("http://", "https://")) else "https://" + u


def es_solo_url(texto: str) -> str | None:
    t = texto.strip()
    if t and RE_URL.fullmatch(t):
        return normalizar_url(t)
    return None


def autolink(texto_escapado: str) -> str:
    def rep(m):
        u = m.group(0)
        return f'<a href="{normalizar_url(html.unescape(u))}" target="_blank" rel="noopener">{u}</a>'
    return RE_URL.sub(rep, texto_escapado)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# --------------------------------------------------------------------------- procesado de archivos
class Procesador:
    def __init__(self, cache: Path, salida: Path, cfg: dict, informe: Informe, raiz: Path):
        self.cache, self.salida, self.cfg, self.inf, self.raiz = cache, salida, cfg, informe, raiz
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.salida / "m").mkdir(parents=True, exist_ok=True)

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.raiz))
        except ValueError:
            return p.name

    def tipo(self, p: Path) -> str | None:
        e = p.suffix.lower()
        if e in EXT_IMAGEN: return "imagen"
        if e in EXT_VIDEO: return "video"
        if e in EXT_TEXTO: return "texto"
        if e in EXT_ENLACE: return "enlace"
        if e in EXT_PDF: return "pdf"
        return None

    def procesar(self, p: Path) -> dict | None:
        t = self.tipo(p)
        if t is None:
            self.inf.aviso(self.rel(p), f"tipo de archivo no soportado ({p.suffix or 'sin extensión'}), se ha ignorado.")
            return None
        try:
            if t == "texto":
                return self._texto(p)
            if t == "enlace":
                return self._enlace_archivo(p)
            return self._binario(p, t)
        except Exception as e:  # un archivo roto no debe tumbar la web
            self.inf.error(self.rel(p), f"no se ha podido procesar ({type(e).__name__}: {e}).")
            return None

    # ----- archivos pesados con caché
    def _binario(self, p: Path, t: str) -> dict | None:
        clave = sha1(p)[:16] + VERSION_CACHE
        meta_p = self.cache / f"{clave}.json"
        if meta_p.exists():
            meta = json.loads(meta_p.read_text())
        else:
            meta = {"imagen": self._imagen, "video": self._video, "pdf": self._pdf}[t](p, clave)
            if meta is None:
                return None
            meta_p.write_text(json.dumps(meta))
        item = dict(meta)
        for campo in ("src", "poster", "miniatura"):
            if campo in item:
                nombre = item[campo]
                destino = self.salida / "m" / nombre
                if not destino.exists():
                    shutil.copy2(self.cache / nombre, destino)
                item[campo] = f"m/{nombre}"
        return item

    def _imagen(self, p: Path, clave: str) -> dict | None:
        ext = p.suffix.lower()
        if ext in {".heic", ".heif"} and not HEIC:
            self.inf.error(self.rel(p), "foto HEIC y falta pillow-heif para convertirla.")
            return None
        lado = self.cfg.get("imagen_lado_max", 2000)
        im = Image.open(p)
        if ext == ".gif":  # se copia tal cual para no romper animación ni transparencia
            nombre = f"{clave}.gif"
            shutil.copy2(p, self.cache / nombre)
            return {"tipo": "imagen", "src": nombre, "w": im.width, "h": im.height}
        im = ImageOps.exif_transpose(im)
        if max(im.size) > lado:
            im.thumbnail((lado, lado), Image.LANCZOS)
        alfa = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        if alfa:
            nombre = f"{clave}.png"
            im.convert("RGBA").save(self.cache / nombre, optimize=True)
        else:
            nombre = f"{clave}.jpg"
            im.convert("RGB").save(self.cache / nombre, quality=self.cfg.get("calidad_jpg", 85), optimize=True, progressive=True)
        return {"tipo": "imagen", "src": nombre, "w": im.width, "h": im.height}

    def _probe(self, p: Path) -> dict:
        r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(p)])
        if r.returncode:
            raise RuntimeError("ffprobe no puede leer el vídeo")
        return json.loads(r.stdout)

    def _dims(self, info: dict) -> tuple[int, int]:
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        w, h = int(v["width"]), int(v["height"])
        rot = 0
        for sd in v.get("side_data_list", []):
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        rot = rot or int(v.get("tags", {}).get("rotate", 0))
        return (h, w) if abs(rot) % 180 == 90 else (w, h)

    def _video(self, p: Path, clave: str) -> dict | None:
        info = self._probe(p)
        vs = [s for s in info["streams"] if s["codec_type"] == "video"]
        if not vs:
            raise RuntimeError("no contiene vídeo")
        v = vs[0]
        a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
        nombre = f"{clave}.mp4"
        dest = self.cache / nombre
        mb = p.stat().st_size / 1e6
        compatible = (p.suffix.lower() in {".mp4", ".m4v", ".mov"} and v.get("codec_name") == "h264"
                      and v.get("pix_fmt") == "yuv420p" and (a is None or a.get("codec_name") in {"aac", "mp3"})
                      and mb <= self.cfg.get("video_mb_sin_recomprimir", 15))
        if compatible:  # solo se reordena para que empiece a reproducirse antes de bajar entero
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(p), "-c", "copy", "-movflags", "+faststart", str(dest)]
        else:
            lado = self.cfg.get("video_lado_max", 1280)
            escala = (f"scale='if(gte(iw,ih),min({lado},iw),-2)':'if(gte(iw,ih),-2,min({lado},ih))',"
                      "scale=trunc(iw/2)*2:trunc(ih/2)*2")
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(p), "-vf", escala, "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", str(self.cfg.get("video_crf", 26)), "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart"]
            cmd += ["-c:a", "aac", "-b:a", "128k"] if a else ["-an"]
            cmd.append(str(dest))
        r = run(cmd)
        if r.returncode:
            raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr else "ffmpeg falló")
        poster = f"{clave}_poster.jpg"
        r = run(["ffmpeg", "-v", "error", "-y", "-i", str(dest), "-frames:v", "1", "-q:v", "4", str(self.cache / poster)])
        w, h = self._dims(self._probe(dest))
        meta = {"tipo": "video", "src": nombre, "w": w, "h": h, "audio": a is not None}
        if r.returncode == 0:
            meta["poster"] = poster
        if dest.stat().st_size > 50e6:
            self.inf.aviso(self.rel(p), f"el vídeo pesa {dest.stat().st_size/1e6:.0f} MB incluso comprimido; mejor subir uno más corto.")
        return meta

    def _pdf(self, p: Path, clave: str) -> dict:
        nombre = f"{clave}.pdf"
        shutil.copy2(p, self.cache / nombre)
        meta = {"tipo": "pdf", "src": nombre}
        try:
            import pymupdf
            doc = pymupdf.open(p)
            z = 600 / max(doc[0].rect.width, 1)  # miniatura de 600 px de ancho
            pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            mini = f"{clave}_mini.jpg"
            Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(self.cache / mini, quality=80)
            meta.update(miniatura=mini, w=pix.width, h=pix.height)
        except Exception:
            pass  # sin miniatura se muestra una tarjeta "PDF"
        return meta

    # ----- textos y enlaces (baratos, sin caché)
    def _enlace_archivo(self, p: Path) -> dict | None:
        url = None
        if p.suffix.lower() == ".url":
            m = re.search(r"^URL=(.+)$", p.read_text(errors="ignore"), re.M)
            url = m and m.group(1).strip()
        else:
            try:
                url = plistlib.loads(p.read_bytes()).get("URL")
            except Exception:
                m = re.search(r"<string>(.+?)</string>", p.read_text(errors="ignore"))
                url = m and m.group(1)
        if not url:
            self.inf.error(self.rel(p), "es un acceso directo pero no tiene ninguna URL dentro.")
            return None
        return self._item_enlace(normalizar_url(url))

    def _item_enlace(self, url: str) -> dict:
        dominio = urlparse(url).netloc.removeprefix("www.")
        return {"tipo": "enlace", "url": url, "dominio": dominio}

    def _texto(self, p: Path) -> dict | None:
        ext = p.suffix.lower()
        if ext == ".docx":
            return self._docx(p)
        raw = p.read_bytes()
        try:
            texto = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = raw.decode("latin-1")
        if url := es_solo_url(texto):
            return self._item_enlace(url)
        if not texto.strip():
            self.inf.aviso(self.rel(p), "el texto está vacío, se ha ignorado.")
            return None
        if ext == ".md":
            import markdown
            cuerpo = markdown.markdown(texto.replace("<", "&lt;"))
            cuerpo = re.sub(r'<a href="', '<a target="_blank" rel="noopener" href="', cuerpo)
        else:
            parrafos = [x for x in re.split(r"\n\s*\n", texto.strip()) if x.strip()]
            cuerpo = "".join(f"<p>{autolink(html.escape(x)).replace(chr(10), '<br>')}</p>" for x in parrafos)
        return {"tipo": "texto", "html": cuerpo}

    def _docx(self, p: Path) -> dict | None:
        from docx import Document
        from docx.text.hyperlink import Hyperlink
        doc = Document(p)
        partes, plano, enlaces = [], [], []
        for par in doc.paragraphs:
            trozos = []
            for c in par.iter_inner_content():
                if isinstance(c, Hyperlink):
                    url = c.address or ""
                    txt = html.escape(c.text)
                    if url:
                        enlaces.append((url, c.text))
                        trozos.append(f'<a href="{html.escape(normalizar_url(url))}" target="_blank" rel="noopener">{txt}</a>')
                    else:
                        trozos.append(txt)
                else:
                    txt = autolink(html.escape(c.text))
                    if c.bold: txt = f"<strong>{txt}</strong>"
                    if c.italic: txt = f"<em>{txt}</em>"
                    trozos.append(txt)
            plano.append(par.text)
            contenido = "".join(trozos).strip()
            if not contenido:
                continue
            estilo = (par.style.name or "").lower() if par.style is not None else ""
            if estilo.startswith(("heading 1", "title", "título")):
                partes.append(f"<h2>{contenido}</h2>")
            elif estilo.startswith(("heading", "subtitle", "encabezado")):
                partes.append(f"<h3>{contenido}</h3>")
            else:
                partes.append(f"<p>{contenido}</p>")
        texto = "\n".join(plano).strip()
        if url := es_solo_url(texto):
            return self._item_enlace(url)
        # Doc corto que es básicamente un único hipervínculo ("Visita la tienda")
        if len(enlaces) == 1 and len(texto) <= len(enlaces[0][1]) + 30:
            return self._item_enlace(normalizar_url(enlaces[0][0]))
        if not texto:
            self.inf.aviso(self.rel(p), "el documento está vacío, se ha ignorado.")
            return None
        return {"tipo": "texto", "html": "".join(partes)}


# --------------------------------------------------------------------------- árbol
class Constructor:
    def __init__(self, proc: Procesador, informe: Informe):
        self.proc, self.inf = proc, informe

    def listar(self, carpeta: Path):
        hijos = sorted((x for x in carpeta.iterdir() if not oculto(x)), key=clave_orden)
        return [x for x in hijos if x.is_file()], [x for x in hijos if x.is_dir()]

    @staticmethod
    def es_icono(p: Path) -> bool:
        return p.stem.strip().lower() == NOMBRE_ICONO and p.suffix.lower() in EXT_IMAGEN | EXT_VIDEO

    def nodo(self, carpeta: Path, ruta_padre: str, usados: set) -> dict | None:
        rel = self.proc.rel(carpeta)
        archivos, subs = self.listar(carpeta)
        iconos = [a for a in archivos if self.es_icono(a)]
        contenido = [a for a in archivos if not self.es_icono(a)]

        # Una sola subcarpeta: se aplana (el clic muestra directamente su contenido)
        while len(subs) == 1:
            a2, subs = self.listar(subs[0])
            iconos += [a for a in a2 if self.es_icono(a)]
            contenido += [a for a in a2 if not self.es_icono(a)]

        if len(iconos) > 1:
            self.inf.aviso(rel, f"hay {len(iconos)} archivos llamados «icono»; se usa {iconos[0].name}.")
        icono = self.proc.procesar(iconos[0]) if iconos else None

        nombre = titulo(carpeta.name)
        slug = unico(slugify(nombre), usados)
        ruta = f"{ruta_padre}/{slug}" if ruta_padre else slug

        items = [i for i in (self.proc.procesar(a) for a in contenido) if i]
        usados_hijos: set = set()
        hijos = [h for h in (self.nodo(s, ruta, usados_hijos) for s in subs) if h]

        n = {"titulo": nombre, "slug": slug, "ruta": ruta}
        if not items and not hijos and not icono:
            self.inf.aviso(rel, "la carpeta está vacía (o nada se ha podido usar); no se ha publicado.")
            usados.discard(slug)
            return None
        if not hijos and not items and icono:  # solo un "icono": se trata como media
            return {**n, "tipo": "media", "icono": icono}
        if not hijos and len(items) == 1 and items[0]["tipo"] == "enlace":
            n.update(tipo="enlace", url=items[0]["url"])
        elif not hijos and len(items) == 1 and items[0]["tipo"] in ("imagen", "video") and not icono:
            return {**n, "tipo": "media", "icono": items[0]}
        else:
            n.update(tipo="carpeta", items=items, hijos=hijos)

        if not icono:
            icono = next((i for i in items if i["tipo"] in ("imagen", "video")), None)
        if not icono:
            icono = next((h["icono"] for h in hijos if h.get("icono")), None)
        if not icono:
            self.inf.aviso(rel, "no hay ninguna imagen ni vídeo para usar como icono; se muestra solo el título.")
        n["icono"] = icono
        return n

    def fondo(self, carpeta: Path) -> list[dict]:
        if not carpeta.is_dir():
            self.inf.aviso("_fondo", "no existe la carpeta _fondo; la portada saldrá sin fondo.")
            return []
        archivos, _ = self.listar(carpeta)
        res = []
        for a in archivos:
            if a.suffix.lower() not in EXT_IMAGEN | EXT_VIDEO:
                self.inf.aviso(self.proc.rel(a), "en _fondo solo se usan imágenes y vídeos.")
                continue
            if (i := self.proc.procesar(a)):
                res.append(i)
        return res


# --------------------------------------------------------------------------- main
def main():
    base = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--media", default="media", help="carpeta con el contenido (copia de Drive)")
    ap.add_argument("--salida", default="site", help="carpeta donde se genera la web")
    ap.add_argument("--config", default=str(base / "config.json"))
    ap.add_argument("--estado", default="ESTADO.txt", help="informe para los editores")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--ajustes", action="store_true", help="muestra siempre el panel de ajustes de la portada")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    media, salida = Path(args.media), Path(args.salida)
    if not media.is_dir():
        sys.exit(f"No existe la carpeta {media}")

    if salida.exists():
        shutil.rmtree(salida)
    shutil.copytree(base / "web", salida)

    inf = Informe()
    proc = Procesador(Path(args.cache), salida, cfg, inf, media)
    cons = Constructor(proc, inf)

    usados: set = set()
    posts = []
    for carpeta in cons.listar(media)[1]:
        if (n := cons.nodo(carpeta, "", usados)):
            posts.append(n)
    for a in cons.listar(media)[0]:
        inf.aviso(a.name, "está suelto fuera de cualquier carpeta; cada post tiene que ser una carpeta.")

    datos = {
        "titulo": cfg.get("titulo", ""),
        "semilla": cfg.get("semilla", 1),
        "portada": cfg.get("portada", {}),
        "ajustes": args.ajustes,
        "generado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fondo": cons.fondo(media / "_fondo"),
        "posts": posts,
    }
    (salida / "contenido.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    estado = inf.texto(len(posts), cfg.get("zona_horaria", "Europe/Madrid"))
    Path(args.estado).write_text(estado, encoding="utf-8")
    print(estado)


if __name__ == "__main__":
    main()
