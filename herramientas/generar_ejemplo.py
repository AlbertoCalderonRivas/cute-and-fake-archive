"""Genera una carpeta media de ejemplo que imita lo que habría en Drive.

Solo sirve para probar el sistema en local:
    python herramientas/generar_ejemplo.py ejemplo_media
Cubre los tres tipos de post y los casos límite.
"""
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import docx.opc.constants

R = random.Random(7)
DEST = Path(sys.argv[1] if len(sys.argv) > 1 else "ejemplo_media")

PASTELES = [(255, 170, 200), (160, 220, 255), (190, 245, 170), (255, 225, 140),
            (210, 180, 255), (255, 190, 150), (150, 240, 220), (250, 250, 250)]


# ---------- personajes animados (gif con transparencia) ----------
def personaje_gif(ruta, semilla, tam=220):
    r = random.Random(semilla)
    cuerpo = r.choice(PASTELES)
    oscuro = tuple(max(0, c - 90) for c in cuerpo)
    acento = r.choice([(255, 80, 120), (60, 120, 255), (40, 180, 90), (255, 150, 0)])
    paleta = [0, 0, 0,  # 0 transparente
              *cuerpo, *oscuro, 255, 255, 255, 20, 20, 20, *acento]
    paleta += [0] * (768 - len(paleta))
    ancho = r.uniform(0.55, 0.8)
    alto = r.uniform(0.5, 0.75)
    patas = r.choice([2, 3, 4])
    antena = r.random() < 0.5
    frames = []
    n = 10
    for i in range(n):
        t = i / n * 2 * math.pi
        im = Image.new("P", (tam, int(tam * 1.15)), 0)
        im.putpalette(paleta)
        d = ImageDraw.Draw(im)
        bote = int(math.sin(t) * tam * 0.04)
        cx, cy = tam / 2, tam * 0.55 + bote
        w, h = tam * ancho / 2, tam * alto / 2
        # patas
        for p in range(patas):
            px = cx - w * 0.6 + p * (w * 1.2 / max(1, patas - 1))
            paso = math.sin(t + p) * tam * 0.03
            d.line([(px, cy + h * 0.7), (px + paso, tam * 1.05)], fill=2, width=max(3, tam // 30))
            d.ellipse([px + paso - 8, tam * 1.05 - 5, px + paso + 10, tam * 1.05 + 5], fill=5)
        # brazos
        sw = math.sin(t * 2) * tam * 0.08
        d.line([(cx - w, cy), (cx - w - tam * 0.12, cy - tam * 0.1 + sw)], fill=2, width=max(3, tam // 35))
        d.line([(cx + w, cy), (cx + w + tam * 0.12, cy - tam * 0.1 - sw)], fill=2, width=max(3, tam // 35))
        if antena:
            d.line([(cx, cy - h), (cx + sw * 0.5, cy - h - tam * 0.15)], fill=2, width=3)
            d.ellipse([cx + sw * 0.5 - 7, cy - h - tam * 0.15 - 7, cx + sw * 0.5 + 7, cy - h - tam * 0.15 + 7], fill=5)
        d.ellipse([cx - w, cy - h, cx + w, cy + h], fill=1, outline=2, width=3)
        # ojos (parpadeo en un frame)
        for s in (-1, 1):
            ex, ey = cx + s * w * 0.38, cy - h * 0.2
            er = tam * 0.09
            if i == 6:
                d.line([(ex - er, ey), (ex + er, ey)], fill=4, width=3)
            else:
                d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=3, outline=4, width=2)
                d.ellipse([ex - er * 0.45, ey - er * 0.2, ex + er * 0.35, ey + er * 0.6], fill=4)
        d.arc([cx - w * 0.25, cy + h * 0.05, cx + w * 0.25, cy + h * 0.45], 10, 170, fill=4, width=3)
        frames.append(im)
    frames[0].save(ruta, save_all=True, append_images=frames[1:], duration=90, loop=0,
                   transparency=0, disposal=2)


def personaje_png(ruta, semilla, tam=500):
    personaje_gif(ruta.with_suffix(".tmp.gif"), semilla, tam)
    im = Image.open(ruta.with_suffix(".tmp.gif")).convert("RGBA")
    im.save(ruta)
    ruta.with_suffix(".tmp.gif").unlink()


# ---------- "fotos" y "screenshots" ----------
def degradado(w, h, arriba, abajo):
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        f = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * f) for a, b in zip(arriba, abajo)))
    return im


def paisaje(w, h, semilla, ui_tiktok=False):
    r = random.Random(semilla)
    cielo = r.choice([((120, 170, 255), (230, 240, 255)), ((255, 140, 90), (255, 220, 170)),
                      ((40, 50, 120), (200, 120, 160)), ((150, 210, 240), (250, 250, 230))])
    im = degradado(w, h, *cielo)
    d = ImageDraw.Draw(im)
    sx, sy, sr = r.uniform(0.2, 0.8) * w, r.uniform(0.15, 0.4) * h, r.uniform(0.05, 0.1) * w
    d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 245, 200))
    for capa in range(3):
        base = h * (0.55 + capa * 0.12)
        color = tuple(int(c * (0.9 - capa * 0.2)) for c in r.choice([(110, 170, 90), (90, 140, 120), (150, 160, 110)]))
        pts = [(0, h)]
        for x in range(0, w + 40, 40):
            pts.append((x, base - r.uniform(0, h * 0.12)))
        pts.append((w, h))
        d.polygon(pts, fill=color)
    if ui_tiktok:
        for k in range(4):
            y = h * (0.5 + k * 0.08)
            d.ellipse([w - 60, y, w - 20, y + 40], fill=(255, 255, 255))
        d.rectangle([20, h - 110, w * 0.65, h - 95], fill=(255, 255, 255))
        d.rectangle([20, h - 80, w * 0.45, h - 68], fill=(235, 235, 235))
        d.rectangle([0, 0, w, 50], fill=(0, 0, 0))
        d.text((20, 18), "16:36", fill=(255, 255, 255))
    return im


def video(ruta, fuente, dur=4, s="540x960", audio=False, codec="libx264"):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{fuente}=s={s}:r=25" if fuente != "gradients" else f"gradients=s={s}:r=25:speed=0.05"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=330"]
    cmd += ["-t", str(dur)]
    if codec == "libx264":
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast"]
    else:
        cmd += ["-c:v", codec, "-q:v", "5"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(ruta)]
    subprocess.run(cmd, check=True)


# ---------- documentos ----------
def _hipervinculo(parrafo, url, texto):
    part = parrafo.part
    rid = part.relate_to(url, docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = texto
    run.append(t)
    h.append(run)
    parrafo._p.append(h)


def doc_texto(ruta):
    d = Document()
    d.add_heading("Sobre Pepito", level=1)
    p = d.add_paragraph("Pepito nació en un ")
    p.add_run("render de baja resolución").bold = True
    p.add_run(" y desde entonces vive en las esquinas de las capturas de pantalla. ")
    p.add_run("No le gusta que le miren directamente.").italic = True
    for _ in range(6):
        d.add_paragraph("Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer posuere erat a ante "
                        "venenatis dapibus posuere velit aliquet. Cras mattis consectetur purus sit amet fermentum. "
                        "Donec ullamcorper nulla non metus auctor fringilla.")
    p = d.add_paragraph("Más información en ")
    _hipervinculo(p, "https://example.com/pepito", "su web oficial")
    p.add_run(" o en https://example.org.")
    d.save(ruta)


def doc_enlace(ruta, url, texto=None):
    d = Document()
    p = d.add_paragraph()
    if texto:
        _hipervinculo(p, url, texto)
    else:
        p.add_run(url)
    d.save(ruta)


def pdf(ruta):
    paginas = []
    for i in range(2):
        im = Image.new("RGB", (1240, 1754), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([100, 100, 1140, 600], fill=(255, 200, 220))
        d.text((120, 650), f"Dossier - pagina {i + 1}", fill="black")
        for k in range(20):
            d.rectangle([120, 720 + k * 40, 120 + R.randint(500, 1000), 735 + k * 40], fill=(200, 200, 200))
        paginas.append(im)
    paginas[0].save(ruta, save_all=True, append_images=paginas[1:])


# ---------- construir el árbol ----------
def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    def carpeta(*partes):
        p = DEST.joinpath(*partes)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Tipo carpeta clásico: icono + una subcarpeta con de todo
    c = carpeta("01 Pepito")
    personaje_gif(c / "icono.gif", 1)
    s = carpeta("01 Pepito", "contenido")
    paisaje(1600, 1200, 11).save(s / "IMG_2041.jpg", quality=90)
    paisaje(1080, 1920, 12, True).save(s / "captura.jpg", quality=90)
    video(s / "clip con sonido.mp4", "mandelbrot", audio=True)
    doc_texto(s / "Sobre Pepito.docx")
    pdf(s / "dossier.pdf")
    doc_enlace(s / "link.docx", "https://www.tiktok.com/@ejemplo/video/123")
    (s / "Tienda.url").write_text("[InternetShortcut]\nURL=https://example.com/tienda\n")
    # Foto de móvil girada por EXIF
    girada = paisaje(3000, 2000, 13)
    exif = Image.Exif(); exif[274] = 6
    girada.save(s / "foto_movil.jpg", quality=88, exif=exif)

    # Tipo enlace: icono + doc con URL (y un archivo no soportado)
    c = carpeta("02 Tienda online")
    personaje_gif(c / "icono.gif", 2)
    doc_enlace(c / "enlace.docx", "https://example.com/tienda")

    # Tipo media: solo un vídeo
    c = carpeta("03 Bucle")
    video(c / "loop.mp4", "gradients", dur=5, s="720x720")

    # Tipo media: solo una imagen png con transparencia
    c = carpeta("04 Flor")
    personaje_png(c / "flor.png", 4)

    # Varias subcarpetas -> tarjetas
    c = carpeta("05 Experimento_01")
    personaje_gif(c / "Icono.GIF", 5)
    s = carpeta("05 Experimento_01", "raw data")
    paisaje(1200, 900, 51).save(s / "datos1.jpg")
    paisaje(900, 1200, 52).save(s / "datos2.jpg")
    (s / "notas.txt").write_text("Mediciones del 12/11.\n\nTodo bastante raro. Ver https://example.com/datos para más.\n", encoding="utf-8")
    s = carpeta("05 Experimento_01", "conclusions")
    personaje_png(s / "icono.png", 55, 300)
    doc_texto(s / "conclusiones.docx")
    paisaje(1200, 1200, 53).save(s / "grafico.jpg")

    # Archivos sueltos sin subcarpeta y sin icono -> carpeta, icono = primera imagen/vídeo
    c = carpeta("06 Paisajes")
    paisaje(1080, 1920, 61, True).save(c / "b_captura.jpg")
    paisaje(1080, 1920, 62, True).save(c / "a_captura.jpg")
    video(c / "c_video.mp4", "life", dur=3, s="540x960")

    # Icono en vídeo + .mov que hay que convertir
    c = carpeta("07 Video icono")
    video(c / "icono.mp4", "cellauto", dur=4, s="480x480")
    video(c / "peli.mov", "testsrc2", dur=3, s="640x360", codec="mpeg4")

    # Sin número delante: va al final
    c = carpeta("Gusano")
    personaje_gif(c / "icono.gif", 8)
    doc_enlace(c / "aqui.docx", "https://example.com/gusano", "Visita la tienda del gusano")

    # Casos de error
    carpeta("08 Vacia")
    c = carpeta("09 Solo texto")
    (c / "poema.txt").write_text("Un texto sin imagen.\nNo hay icono posible.", encoding="utf-8")
    c = carpeta("02 Tienda online")
    (c / "presupuesto.pages").write_bytes(b"no soportado")

    # Oculta
    c = carpeta("_borrador")
    personaje_gif(c / "icono.gif", 9)

    # Más personajes para llenar la portada (algunos media, otros carpeta)
    nombres = ["10 Bichito", "11 Ramona", "12 Señor Bola", "13 Lili", "14 Tuerca", "15 Chicle",
               "16 Moco", "17 Nube", "18 Patata"]
    for k, nombre in enumerate(nombres):
        c = carpeta(nombre)
        if k % 3 == 1:
            personaje_gif(c / "icono.gif", 100 + k, tam=R.randint(160, 260))
            paisaje(1200, 900, 200 + k).save(c / "foto.jpg")
            paisaje(900, 1200, 300 + k).save(c / "foto2.jpg")
        else:
            personaje_gif(c / f"{nombre.split()[1].lower()}.gif", 100 + k, tam=R.randint(160, 260))

    # Fondo
    f = carpeta("_fondo")
    for k in range(9):
        paisaje(720, 1280, 900 + k, True).save(f / f"screenshot_{k}.jpg", quality=85)

    print("Ejemplo generado en", DEST)


if __name__ == "__main__":
    main()
