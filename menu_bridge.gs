// Together Menu Bridge — forwards new weekly menu PDFs into the GitHub repo, where the
// "Update menu from PDF" Action extracts them into menus/<date>.json, deletes the PDF and redeploys the app.
// (Sent files are remembered here by Drive ID / Gmail label, so a deleted PDF is not re-sent.)
//
// Two inputs, use either or both:
//   • Google Drive: any PDF dropped into the folder whose ID is in script property DRIVE_FOLDER_ID
//   • Gmail:        any PDF attachment on an email matching GMAIL_QUERY (e.g. forward the canteen's email)
//
// Setup (once), in a standalone Apps Script project (script.google.com → New project):
//   1. Paste this file as Code.gs.
//   2. Project Settings (⚙) → Script properties:
//        GITHUB_TOKEN     = a GitHub fine-grained token for the repo with "Contents: Read and write"
//        DRIVE_FOLDER_ID  = the ID from the Drive folder URL  (optional if only using Gmail)
//   3. Run checkForNewMenus once from the editor and grant Drive/Gmail access.
//   4. Triggers (⏰) → Add trigger: checkForNewMenus, time-driven, every 15 minutes.

var REPO = 'SimonChan1070/TogtherRating';
var BRANCH = 'main';
var GMAIL_QUERY = 'has:attachment filename:pdf subject:"Together menu" newer_than:14d';
var DONE_LABEL = 'TogetherMenu/Uploaded';

function checkForNewMenus() {
  checkDrive();
  checkGmail();
}

function props_() { return PropertiesService.getScriptProperties(); }

function checkDrive() {
  var folderId = props_().getProperty('DRIVE_FOLDER_ID');
  if (!folderId) return;
  var seen = JSON.parse(props_().getProperty('DRIVE_SEEN') || '{}');
  var files = DriveApp.getFolderById(folderId).getFilesByType(MimeType.PDF);
  while (files.hasNext()) {
    var f = files.next();
    if (seen[f.getId()]) continue;
    if (uploadToGitHub_(f.getName(), f.getBlob())) seen[f.getId()] = new Date().toISOString();
  }
  props_().setProperty('DRIVE_SEEN', JSON.stringify(seen));
}

function checkGmail() {
  var label = GmailApp.getUserLabelByName(DONE_LABEL) || GmailApp.createLabel(DONE_LABEL);
  GmailApp.search(GMAIL_QUERY).forEach(function (thread) {
    if (thread.getLabels().some(function (l) { return l.getName() === DONE_LABEL; })) return;
    var uploaded = false;
    thread.getMessages().forEach(function (msg) {
      msg.getAttachments().forEach(function (att) {
        if (att.getContentType() === 'application/pdf' || /\.pdf$/i.test(att.getName())) {
          if (uploadToGitHub_(att.getName(), att)) uploaded = true;
        }
      });
    });
    if (uploaded) thread.addLabel(label);
  });
}

// Creates or updates menus/<name> on GitHub via the Contents API. A push from a personal token
// triggers the repo's Actions, so the extractor runs automatically.
function uploadToGitHub_(name, blob) {
  var token = props_().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Script property GITHUB_TOKEN is missing');
  var safe = name.replace(/[^\w .()\-]+/g, '_');
  var url = 'https://api.github.com/repos/' + REPO + '/contents/menus/' + encodeURIComponent(safe);
  var headers = { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' };

  var existing = UrlFetchApp.fetch(url + '?ref=' + BRANCH, { headers: headers, muteHttpExceptions: true });
  var body = { message: 'Menu PDF: ' + safe, branch: BRANCH, content: Utilities.base64Encode(blob.getBytes()) };
  if (existing.getResponseCode() === 200) body.sha = JSON.parse(existing.getContentText()).sha;

  var res = UrlFetchApp.fetch(url, {
    method: 'put', contentType: 'application/json', headers: headers,
    payload: JSON.stringify(body), muteHttpExceptions: true
  });
  var code = res.getResponseCode();
  if (code === 200 || code === 201) { Logger.log('Uploaded menus/' + safe); return true; }
  Logger.log('GitHub upload failed (' + code + '): ' + res.getContentText());
  return false;
}
