// Team mascots are optional images in static/mascotes/, kept out of git. A
// lista.js next to them sets window.MASCOTS_LIST to the keywords; a team whose
// name contains one (ignoring case and accents) gets that keyword's .jpg.
// Without the list nothing is shown. Shared by the tournament page and the
// "against a team" match panel.
const MASCOTS = window.MASCOTS_LIST || [];

function mascot(teamName, size) {
  const plain = String(teamName).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const key = MASCOTS.find(k => plain.includes(k));
  return key ? `<img class="mascot ${size}" src="/static/mascotes/${key}.jpg" alt="" loading="lazy">` : "";
}
