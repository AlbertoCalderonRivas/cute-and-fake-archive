/**
 * Vigila la carpeta "media" de Drive y avisa a GitHub cuando cambia.
 *
 * Instalación (una sola vez):
 *  1. script.google.com → Nuevo proyecto → pega este archivo.
 *  2. Configuración del proyecto (⚙️) → Propiedades del script → añade:
 *       CARPETA_ID    el ID de la carpeta media (lo que va tras /folders/ en la URL)
 *       GITHUB_REPO   usuario/repositorio   (ej. "maria/cute-and-fake")
 *       GITHUB_TOKEN  token "fine-grained" de GitHub con permiso Contents: Read and write
 *                     solo sobre ese repositorio
 *  3. Ejecuta la función `instalar` una vez y acepta los permisos.
 *
 * Funcionamiento: cada 5 minutos calcula una "huella" de la carpeta (nombres, fechas
 * y tamaños de todo lo que hay dentro). Si ha cambiado, espera a la siguiente revisión
 * para asegurarse de que nadie sigue subiendo cosas, y entonces avisa a GitHub.
 */

const MINUTOS = 5;
const ARCHIVO_ESTADO = '_ESTADO.txt';

function instalar() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('revisar').timeBased().everyMinutes(MINUTOS).create();
  asegurarEstado_('Sistema instalado. La primera publicación se hará en unos minutos.\n');
  PropertiesService.getScriptProperties().deleteProperty('PUBLICADA');
  revisar();
}

function revisar() {
  const props = PropertiesService.getScriptProperties();
  const carpeta = DriveApp.getFolderById(props.getProperty('CARPETA_ID'));
  const huella = huella_(carpeta);

  const vista = props.getProperty('VISTA');         // la de la revisión anterior
  const publicada = props.getProperty('PUBLICADA'); // la última que se mandó publicar

  if (huella !== vista) {          // hay cambios recientes: esperar a que terminen de subir
    props.setProperty('VISTA', huella);
    return;
  }
  if (huella === publicada) return; // nada nuevo

  avisarGitHub_(props);
  props.setProperty('PUBLICADA', huella);
  asegurarEstado_('⏳ Actualizando la web… (' + ahora_() + ')\nEn unos minutos aquí aparecerá el resultado.\n');
}

/** Lanzar a mano una publicación aunque no haya cambios. */
function publicarAhora() {
  avisarGitHub_(PropertiesService.getScriptProperties());
}

function avisarGitHub_(props) {
  const repo = props.getProperty('GITHUB_REPO');
  const r = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + props.getProperty('GITHUB_TOKEN'),
      Accept: 'application/vnd.github+json',
    },
    payload: JSON.stringify({ event_type: 'drive-actualizado' }),
    muteHttpExceptions: true,
  });
  if (r.getResponseCode() !== 204) {
    throw new Error('GitHub respondió ' + r.getResponseCode() + ': ' + r.getContentText());
  }
}

function huella_(carpeta) {
  const partes = [];
  (function recorrer(c, ruta) {
    const archivos = c.getFiles();
    while (archivos.hasNext()) {
      const f = archivos.next();
      if (ruta === '' && f.getName() === ARCHIVO_ESTADO) continue; // lo escribimos nosotros
      partes.push(ruta + f.getName() + '|' + f.getLastUpdated().getTime() + '|' + f.getSize());
    }
    const subs = c.getFolders();
    while (subs.hasNext()) {
      const s = subs.next();
      partes.push(ruta + s.getName() + '/');
      recorrer(s, ruta + s.getName() + '/');
    }
  })(carpeta, '');
  partes.sort();
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, partes.join('\n'));
  return Utilities.base64Encode(bytes);
}

/** El archivo de estado lo crea este script (con tu cuenta), y GitHub solo lo sobrescribe. */
function asegurarEstado_(texto) {
  const props = PropertiesService.getScriptProperties();
  const carpeta = DriveApp.getFolderById(props.getProperty('CARPETA_ID'));
  const it = carpeta.getFilesByName(ARCHIVO_ESTADO);
  if (it.hasNext()) it.next().setContent(texto);
  else carpeta.createFile(ARCHIVO_ESTADO, texto, MimeType.PLAIN_TEXT);
}

function ahora_() {
  return Utilities.formatDate(new Date(), 'Europe/Madrid', 'dd/MM/yyyy HH:mm');
}
