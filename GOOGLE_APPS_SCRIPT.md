# Google Apps Script for Blue Tigers Equipment Sign Out

Replace the contents of `Code.gs` in the Google Apps Script project linked to the
equipment spreadsheet with the code below. It keeps the live records in the
existing tabs and adds a permanent `Deleted Records` audit tab. Deleted records
are appended to that tab before the website removes them from the live site.

```javascript
const API_TOKEN = 'PASTE_THE_SAME_SECRET_USED_IN_RENDER_HERE';
const LIVE_HEADERS = [
  'Record ID', 'Cadet', 'Pickup Date', 'Return Date', 'Status', 'Items',
  'Created At', 'Record JSON'
];
const LINE_ITEM_HEADERS = [
  'Record ID', 'Cadet', 'Item', 'Quantity', 'Pickup Date', 'Return Date', 'Status'
];
const NOTE_HEADERS = ['Record ID', 'Cadet', 'Staff Notes', 'Issue Details', 'Updated At'];
const DELETED_RECORD_HEADERS = [
  'Deleted At', 'Deleted By', 'Final Stage', 'Record ID', 'Cadet',
  'Pickup Date', 'Return Date', 'Items', 'Created At', 'Returned At',
  'Return Type', 'Missing Items', 'Staff Confirmed', 'Staff Confirmed At',
  'Staff Issue', 'Issue Details', 'Issue Logged At', 'Staff Notes',
  'Pickup Available At', 'Record JSON'
];

function setup() {
  ensureSheet_('Equipment Records', LIVE_HEADERS);
  ensureSheet_('Line Items', LINE_ITEM_HEADERS);
  ensureSheet_('Admin Notes', NOTE_HEADERS);
  ensureSheet_('Deleted Records', DELETED_RECORD_HEADERS);
}

function doGet(e) {
  try {
    verifyToken_(e.parameter.token);
    const sheet = ensureSheet_('Equipment Records', LIVE_HEADERS);
    const rows = sheet.getDataRange().getValues();
    if (rows.length < 2) return json_({ok: true, records: []});
    const jsonColumn = rows[0].indexOf('Record JSON');
    const records = rows.slice(1).map(row => {
      try { return JSON.parse(row[jsonColumn]); } catch (error) { return null; }
    }).filter(Boolean);
    return json_({ok: true, records: records});
  } catch (error) {
    return json_({ok: false, error: error.message});
  }
}

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents || '{}');
    verifyToken_(payload.token);
    if (payload.action === 'archive_record') {
      if (!payload.record || typeof payload.record !== 'object') {
        throw new Error('A record is required for the deletion archive.');
      }
      archiveDeletedRecord_(payload);
      return json_({ok: true});
    }
    if (!Array.isArray(payload.records)) throw new Error('A records list is required.');
    writeLiveRecords_(payload.records);
    return json_({ok: true});
  } catch (error) {
    return json_({ok: false, error: error.message});
  }
}

function writeLiveRecords_(records) {
  const liveRows = records.map(record => [
    value_(record.id), value_(record.cadet_name), value_(record.pickup_date),
    value_(record.return_date), statusFor_(record), itemsText_(record.items),
    value_(record.created_at), JSON.stringify(record)
  ]);
  replaceRows_('Equipment Records', LIVE_HEADERS, liveRows);

  const itemRows = [];
  records.forEach(record => (record.items || []).forEach(item => itemRows.push([
    value_(record.id), value_(record.cadet_name), value_(item.name), value_(item.quantity),
    value_(record.pickup_date), value_(record.return_date), statusFor_(record)
  ])));
  replaceRows_('Line Items', LINE_ITEM_HEADERS, itemRows);

  const noteRows = records.map(record => [
    value_(record.id), value_(record.cadet_name), value_(record.staff_notes),
    value_(record.issue_details), value_(record.staff_confirmed_at || record.issue_logged_at)
  ]);
  replaceRows_('Admin Notes', NOTE_HEADERS, noteRows);
}

function archiveDeletedRecord_(payload) {
  const record = payload.record;
  const row = [
    value_(payload.deleted_at || new Date().toISOString()), value_(payload.deleted_by || 'Admin'),
    value_(payload.final_stage || statusFor_(record)), value_(record.id),
    value_(record.cadet_name), value_(record.pickup_date), value_(record.return_date),
    itemsText_(record.items), value_(record.created_at), value_(record.returned_at),
    value_(record.return_type), value_(record.missing_items), value_(record.staff_confirmed),
    value_(record.staff_confirmed_at), value_(record.staff_issue), value_(record.issue_details),
    value_(record.issue_logged_at), value_(record.staff_notes),
    value_(record.pickup_available_at), JSON.stringify(record)
  ];
  const sheet = ensureSheet_('Deleted Records', DELETED_RECORD_HEADERS);
  sheet.appendRow(row);
}

function replaceRows_(name, headers, rows) {
  const sheet = ensureSheet_(name, headers);
  sheet.clearContents();
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  if (rows.length) sheet.getRange(2, 1, rows.length, headers.length).setValues(rows);
  formatSheet_(sheet, headers.length);
}

function ensureSheet_(name, headers) {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = spreadsheet.getSheetByName(name) || spreadsheet.insertSheet(name);
  if (sheet.getLastRow() === 0) sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  formatSheet_(sheet, headers.length);
  return sheet;
}

function formatSheet_(sheet, columns) {
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, columns).setFontWeight('bold').setBackground('#356b96').setFontColor('#ffffff');
  sheet.autoResizeColumns(1, columns);
}

function statusFor_(record) {
  if (truthy_(record.staff_confirmed)) return 'returned';
  if (truthy_(record.return_claimed)) return 'pending-review';
  const pickupAvailableAt = record.pickup_available_at ||
    (record.pickup_date ? `${record.pickup_date}T08:00:00` : '');
  if (!truthy_(record.picked_up) && pickupAvailableAt && new Date() < new Date(pickupAvailableAt)) {
    return 'waiting-pickup';
  }
  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  return record.return_date && record.return_date < today ? 'late' : 'checked-out';
}

function itemsText_(items) {
  return (items || []).map(item => `${value_(item.quantity)} ${value_(item.name)}`).join(', ');
}

function truthy_(value) {
  return value === true || value === 1 || String(value).toLowerCase() === 'true' || String(value) === '1';
}

function value_(value) { return value == null ? '' : String(value); }

function verifyToken_(token) {
  if (!API_TOKEN || token !== API_TOKEN) throw new Error('Unauthorized.');
}

function json_(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}
```

After saving, use **Deploy → Manage deployments → Edit → New version → Deploy**.
The existing web-app URL stays the same.
