// Together Rating DB — web endpoint for the Today Together Rating app
// (deployed from the Apps Script project "Together Rating API" bound to the Google Sheet "Together Rating DB")
// POST JSON {date, meal, food, rating, score, comment, name} -> appends a row
// GET ?date=yyyy-mm-dd -> JSON array of ratings (all rows if no date)
var SHEET_NAME = 'Ratings';

function sheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(SHEET_NAME) || ss.getSheets()[0];
}

// Sheets turns '2026-09-18' text into a real date; normalise both back to yyyy-MM-dd
function fmt_(v) {
  if (v && typeof v.getTime === 'function') return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  return String(v || '').slice(0, 10);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    var d = JSON.parse(e.postData.contents);
    if (!d.date || !d.meal || !d.food || !d.rating) return json_({ ok: false, error: 'missing fields' });
    var lock = LockService.getScriptLock();
    lock.waitLock(10000);
    sheet_().appendRow([new Date(), String(d.date), String(d.meal), String(d.food), String(d.rating),
      Number(d.score) || 0, String(d.comment || ''), String(d.name || '')]);
    lock.releaseLock();
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function doGet(e) {
  var rows = sheet_().getDataRange().getValues();
  rows.shift(); // header
  var want = e && e.parameter && e.parameter.date;
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    if (!r[1]) continue;
    var date = fmt_(r[1]);
    if (want && date !== want) continue;
    out.push({ ts: r[0], date: date, meal: r[2], food: r[3], rating: r[4], score: Number(r[5]) || 0, comment: r[6], name: r[7] });
  }
  return json_(out);
}
