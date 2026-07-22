from __future__ import annotations

import html
import json
import os
from datetime import date, datetime, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4


BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "equipment_log.json"
STYLE_FILE = BASE_DIR / "static" / "styles.css"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "BlueTigers26")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))


def load_records() -> list[dict]:
    if not DATA_FILE.exists():
        DATA_FILE.parent.mkdir(exist_ok=True)
        DATA_FILE.write_text("[]", encoding="utf-8")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_records(records: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")


def today_iso() -> str:
    return date.today().isoformat()


def min_buffer_date() -> date:
    return (now() + timedelta(hours=72)).date()


def min_buffer_iso() -> str:
    return min_buffer_date().isoformat()


def now() -> datetime:
    return datetime.now()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def display_dt(value: str | None) -> str:
    parsed = parse_dt(value)
    if not parsed:
        return ""
    return parsed.strftime("%b %d, %Y at %I:%M %p").replace(" 0", " ")


def duration_between(start: str | None, end: str | None) -> str:
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)
    if not start_dt or not end_dt:
        return "Not checked yet"
    minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours} hr {mins} min"
    return f"{mins} min"


def parse_date(value: str | None) -> date:
    if not value:
        return min_buffer_date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return min_buffer_date()


def safe_request_dates(pickup_value: str | None, return_value: str | None) -> tuple[str, str]:
    minimum = min_buffer_date()
    pickup = max(parse_date(pickup_value), minimum)
    return_date = max(parse_date(return_value), minimum)
    if return_date < pickup:
        return_date = pickup
    return pickup.isoformat(), return_date.isoformat()


def return_sort_key(record: dict) -> tuple[str, str]:
    return (record.get("return_date") or "9999-12-31", record.get("pickup_date") or "9999-12-31")


def recent_staff_return(record: dict) -> bool:
    confirmed_at = parse_dt(record.get("staff_confirmed_at"))
    if not confirmed_at:
        return False
    return now() - confirmed_at <= timedelta(hours=24)


def pickup_available_at(record: dict) -> str:
    pickup_date = record.get("pickup_date")
    if pickup_date:
        return f"{pickup_date}T08:00:00"
    existing = record.get("pickup_available_at")
    if existing:
        return existing
    created = parse_dt(record.get("created_at")) or now()
    return (created + timedelta(hours=72)).isoformat(timespec="seconds")


def status_for(record: dict) -> str:
    if record.get("staff_confirmed"):
        return "returned"
    if not record.get("picked_up"):
        return "waiting-pickup"
    due = record.get("return_date") or today_iso()
    if due < today_iso():
        return "late"
    if record.get("return_claimed"):
        return "pending-review"
    return "checked-out"


def enrich(records: list[dict]) -> list[dict]:
    enriched = []
    for record in records:
        item = dict(record)
        item["status"] = status_for(record)
        item["pickup_available_at"] = pickup_available_at(record)
        item["pickup_available_display"] = display_dt(item["pickup_available_at"])
        item["returned_at_display"] = display_dt(record.get("returned_at"))
        item["review_duration"] = duration_between(record.get("returned_at"), record.get("staff_confirmed_at"))
        item["items_text"] = ", ".join(
            f"{line['quantity']} {line['name']}" for line in item.get("items", [])
        )
        enriched.append(item)
    return enriched


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def layout(title: str, body: str, admin: bool = False) -> bytes:
    nav_admin = '<a href="/admin">Admin</a><a href="/logout">Logout</a>' if admin else '<a href="/login">Admin Login</a>'
    page = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{esc(title)} | Blue Tigers Equipment Store</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    <header class="topbar">
      <a class="brand" href="/">Blue Tigers Equipment Sign Out</a>
      <nav>
        <a href="/signout">Sign Out</a>
        <a href="/return">Return</a>
        {nav_admin}
      </nav>
    </header>
    <main>{body}</main>
    <script>
      function updateCountdowns() {{
        document.querySelectorAll("[data-deadline]").forEach((node) => {{
          const deadline = new Date(node.dataset.deadline);
          const diff = deadline - new Date();
          if (Number.isNaN(deadline.getTime())) return;
          if (diff <= 0) {{
            node.textContent = "Overdue";
            node.classList.add("overdue");
            return;
          }}
          const totalMinutes = Math.floor(diff / 60000);
          const days = Math.floor(totalMinutes / 1440);
          const hours = Math.floor((totalMinutes % 1440) / 60);
          const minutes = totalMinutes % 60;
          node.textContent = `${{days}}d ${{hours}}h ${{minutes}}m remaining`;
        }});
      }}
      updateCountdowns();
      setInterval(updateCountdowns, 60000);
    </script>
  </body>
</html>"""
    return page.encode("utf-8")


def home_page(admin: bool = False) -> bytes:
    records = enrich(load_records())
    active = [r for r in records if r["status"] in {"waiting-pickup", "checked-out", "late", "pending-review"}]
    late_count = len([r for r in records if r["status"] == "late"])
    review_count = len([r for r in records if r["status"] == "pending-review"])
    body = f"""
<section class="hero">
  <div>
    <p class="eyebrow">Logistics accountability</p>
    <h1>Request, track, and return equipment in one place.</h1>
    <p class="intro">Cadets can sign equipment out or report returned items. Staff can review claimed returns, late equipment, current checkouts, and upcoming pickups.</p>
  </div>
  <div class="summary-grid">
    <div><strong>{len(active)}</strong><span>Active items</span></div>
    <div><strong>{late_count}</strong><span>Late returns</span></div>
    <div><strong>{review_count}</strong><span>Need review</span></div>
  </div>
</section>
<section class="action-grid" aria-label="Main actions">
  <a class="action-card admin" href="/login"><span>Admin</span><strong>Review equipment</strong><small>Confirm returns, mark issues, and see late items.</small></a>
  <a class="action-card signout" href="/signout"><span>Cadet</span><strong>Sign out equipment</strong><small>Log who needs what, when it leaves, and when it comes back.</small></a>
  <a class="action-card return" href="/return"><span>Cadet</span><strong>Return equipment</strong><small>Report a full or partial return for staff confirmation.</small></a>
</section>"""
    return layout("Home", body, admin)


def signout_page(admin: bool = False) -> bytes:
    earliest = now() + timedelta(hours=72)
    earliest_display = earliest.strftime("%b %d, %Y at %I:%M %p").replace(" 0", " ")
    min_date = min_buffer_iso()
    body = f"""
<section class="panel">
  <div class="panel-heading"><p class="eyebrow">Equipment request</p><h1>Sign Out Equipment</h1></div>
  <form method="post" class="form-stack" id="signout-form">
    <label>Cadet last name<input name="cadet" required placeholder="C/Lastname"></label>
    <div class="two-col">
      <label>Pickup date<input type="date" name="pickup_date" value="{min_date}" min="{min_date}" required></label>
      <label>Return date<input type="date" name="return_date" value="{min_date}" min="{min_date}" required></label>
    </div>
    <label>Why is the equipment needed?<textarea name="reason" rows="3" required placeholder="LLAB, AAS, Color Guard, flight sim setup..."></textarea></label>
    <div class="line-items" id="line-items">
      <div class="item-row">
        <label>Equipment item<input name="item_name" required placeholder="Item name"></label>
        <label>Quantity<input name="quantity" type="number" min="1" value="1" required></label>
        <button class="remove-row" type="button">Remove</button>
      </div>
    </div>
    <button class="secondary" type="button" id="add-item">Add another equipment item</button>
    <div class="submit-row">
      <button type="submit">Submit request</button>
      <div class="notice">Earliest pickup: <strong>{esc(earliest_display)}</strong></div>
    </div>
    <p class="short-notice">If equipment needs to be picked up before the 72 hour buffer, a message must be sent to C/Devens and C/Nettles describing what the equipment is needed for, and why on such short notice. Equipment will not be allowed to be taken without permission from either C/Devens or C/Nettles.</p>
  </form>
</section>
<script>
function refreshRemoveButtons() {{
  const rows = document.querySelectorAll(".item-row");
  rows.forEach((row) => {{
    row.querySelector(".remove-row").disabled = rows.length === 1;
  }});
}}
document.querySelector("#add-item").addEventListener("click", () => {{
  const row = document.querySelector(".item-row").cloneNode(true);
  row.querySelectorAll("input").forEach((input) => {{ input.value = input.type === "number" ? "1" : ""; }});
  document.querySelector("#line-items").appendChild(row);
  refreshRemoveButtons();
}});
document.querySelector("#line-items").addEventListener("click", (event) => {{
  if (!event.target.classList.contains("remove-row")) return;
  const rows = document.querySelectorAll(".item-row");
  if (rows.length > 1) event.target.closest(".item-row").remove();
  refreshRemoveButtons();
}});
refreshRemoveButtons();
</script>"""
    return layout("Sign Out", body, admin)


def return_page(admin: bool = False) -> bytes:
    open_records = sorted(
        [r for r in enrich(load_records()) if r["status"] in {"checked-out", "late", "waiting-pickup"}],
        key=return_sort_key,
    )
    if not open_records:
        form = '<div class="empty-state">No open equipment records are ready for return.</div>'
    else:
        options = '<option value="" selected disabled>Select a return request</option>'
        for record in open_records:
            items_json = json.dumps(record["items"]).replace("<", r"\u003c")
            options += (
                f'<option value="{esc(record["id"])}" data-items="{esc(items_json)}">'
                f'{esc(record["cadet"])} | Return {esc(record["return_date"])}'
                f'</option>'
            )
        form = f"""
<form method="post" class="form-stack">
  <label>Request<select name="record_id" id="return-request" required>{options}</select></label>
  <section class="return-items" id="return-items" hidden aria-live="polite">
    <h2>Equipment to Return</h2>
    <ul id="return-items-list"></ul>
  </section>
  <label class="checkbox"><input type="radio" name="return_type" value="all" checked>Returning all equipment</label>
  <label class="checkbox"><input type="radio" name="return_type" value="partial">Returning only some of the items</label>
  <label>List the items not being returned, including damaged or broken items<textarea name="missing_items" rows="6" placeholder="Leave blank if everything was returned in good condition."></textarea></label>
  <button type="submit">Submit return report</button>
</form>
<script>
const returnRequest = document.querySelector("#return-request");
const returnItems = document.querySelector("#return-items");
const returnItemsList = document.querySelector("#return-items-list");

function showReturnItems() {{
  const selected = returnRequest.options[returnRequest.selectedIndex];
  const items = selected?.dataset.items ? JSON.parse(selected.dataset.items) : [];
  returnItemsList.replaceChildren();
  items.forEach((item) => {{
    const line = document.createElement("li");
    line.textContent = item.quantity + " x " + item.name;
    returnItemsList.appendChild(line);
  }});
  returnItems.hidden = items.length === 0;
}}

returnRequest.addEventListener("change", showReturnItems);
</script>"""
    body = f'<section class="panel"><div class="panel-heading"><p class="eyebrow">Cadet return report</p><h1>Return Equipment</h1></div>{form}</section>'
    return layout("Return", body, admin)


def login_page(error: str = "", admin: bool = False) -> bytes:
    error_html = f'<p class="error">{esc(error)}</p>' if error else ""
    body = f"""
<section class="panel narrow">
  <div class="panel-heading"><p class="eyebrow">Staff only</p><h1>Admin Login</h1></div>
  <form method="post" class="form-stack">
    <label>Username<input name="username" value="admin" autocomplete="username"></label>
    <label>Password<input type="password" name="password" autocomplete="current-password" required></label>
    {error_html}
    <button type="submit">Login</button>
  </form>
</section>"""
    return layout("Admin Login", body, admin)


def read_record(record: dict) -> str:
    return f"""
<div class="record status-{esc(record["status"])}">
  <div>
    <strong>{esc(record["cadet"])}</strong>
    <span>{esc(record["items_text"])}</span>
    <small>Pickup {esc(record["pickup_date"])} | Return {esc(record["return_date"])}</small>
    <small>{esc(record["reason"])}</small>
  </div>
</div>"""


def note_lines(record: dict) -> str:
    lines = []
    if record.get("missing_items"):
        lines.append(f'<small>Missing/damaged from return: {esc(record["missing_items"])}</small>')
    if record.get("staff_notes"):
        lines.append(f'<small>Notes: {esc(record["staff_notes"])}</small>')
    if record.get("issue_details"):
        lines.append(f'<small>Broken/missing log: {esc(record["issue_details"])}</small>')
    if record.get("returned_at"):
        lines.append(f'<small>Time returned by user: {esc(record["returned_at_display"])}</small>')
        lines.append(f'<small>Time to check returned equipment: {esc(record["review_duration"])}</small>')
    if record["status"] == "waiting-pickup":
        lines.append(
            f'<small>Pickup opens: {esc(record["pickup_available_display"])} '
            f'<span class="countdown" data-deadline="{esc(record["pickup_available_at"])}"></span></small>'
        )
    return "".join(lines)


def admin_record(record: dict) -> str:
    ready = "checked" if record.get("ready_for_pickup") else ""
    confirmed = "checked" if record.get("staff_confirmed") else ""
    issue = "checked" if record.get("staff_issue") else ""
    return f"""
<form method="post" class="record status-{esc(record["status"])}">
  <input type="hidden" name="record_id" value="{esc(record["id"])}">
  <div>
    <strong>{esc(record["cadet"])}</strong>
    <span>{esc(record["items_text"])}</span>
    <small>Pickup {esc(record["pickup_date"])} | Return {esc(record["return_date"])}</small>
    {note_lines(record)}
  </div>
  <label class="checkbox"><input type="checkbox" name="ready_for_pickup" {ready}>Ready for pick-up</label>
  <label class="checkbox"><input type="checkbox" name="staff_confirmed" {confirmed}>Returned</label>
  <label class="checkbox"><input type="checkbox" name="staff_issue" {issue}>Broken, missing, or misplaced</label>
  <input name="issue_details" value="{esc(record.get("issue_details"))}" placeholder="Missing items">
  <input name="staff_notes" placeholder="Additional details">
  <button type="submit">Update</button>
</form>"""


def issue_record(record: dict) -> str:
    tracked = display_dt(record.get("issue_logged_at")) or "Not timestamped"
    return f"""
<form method="post" class="record issue-log status-late" onsubmit="return confirm('Remove this item from the broken, missing, or misplaced equipment list?');">
  <input type="hidden" name="record_id" value="{esc(record["id"])}">
  <input type="hidden" name="action" value="clear_issue">
  <div>
    <strong>{esc(record["cadet"])}</strong>
    <span>{esc(record.get("issue_details"))}</span>
    <small>Original checkout: {esc(record["items_text"])}</small>
    <small>Tracked as broken/missing: {esc(tracked)}</small>
  </div>
  <label class="checkbox"><input type="checkbox" required>Confirm removal</label>
  <button class="danger" type="submit">Remove</button>
</form>"""


def admin_page(admin: bool = True) -> bytes:
    records = enrich(load_records())
    buckets = {
        "scheduled": sorted([r for r in records if r["status"] == "waiting-pickup" and not r.get("ready_for_pickup")], key=return_sort_key),
        "ready": sorted([r for r in records if r["status"] == "waiting-pickup" and r.get("ready_for_pickup")], key=return_sort_key),
        "returned": sorted([r for r in records if r["status"] == "pending-review"], key=return_sort_key),
        "complete": sorted([r for r in records if r["status"] == "returned" and recent_staff_return(r)], key=return_sort_key),
        "late": sorted([r for r in records if r["status"] == "late"], key=return_sort_key),
        "out": sorted([r for r in records if r["status"] == "checked-out"], key=return_sort_key),
        "issues": sorted([r for r in records if r.get("staff_issue") and r.get("issue_details")], key=return_sort_key),
    }

    def section(key: str, title: str, renderer, empty: str) -> str:
        rows = "".join(renderer(record) for record in buckets[key])
        return f'<section id="{key}" class="admin-section"><h2>{title}</h2>{rows or f"<p class=\"empty-state\">{empty}</p>"}</section>'

    body = f"""
<section class="panel wide">
  <div class="panel-heading"><p class="eyebrow">Staff dashboard</p><h1>Admin Screen</h1></div>
  <div class="tabs">
    <a href="#scheduled">Equipment to be Signed Out</a>
    <a href="#ready">Ready for Pick-up</a>
    <a href="#returned">Equipment Returned</a>
    <a href="#late">Late Equipment</a>
    <a href="#complete">Returned Items</a>
    <a href="#out">Equipment Currently Out</a>
    <a href="#issues">Broken, Missing, or Misplaced Equipment</a>
  </div>
  {section("scheduled", "Equipment to be Signed Out", admin_record, "No upcoming pickups are scheduled.")}
  {section("ready", "Ready for Pick-up", admin_record, "No equipment is marked ready for pick-up.")}
  {section("returned", "Equipment Returned", admin_record, "No returned items are waiting on staff confirmation.")}
  {section("late", "Late Equipment", admin_record, "Nothing is late right now.")}
  {section("complete", "Returned Items", admin_record, "No staff-confirmed returns from the last 24 hours.")}
  {section("out", "Equipment Currently Out", admin_record, "No equipment is currently checked out.")}
  {section("issues", "Broken, Missing, or Misplaced Equipment", issue_record, "No broken, missing, or misplaced equipment has been logged.")}
</section>"""
    return layout("Admin", body, admin)


class EquipmentHandler(BaseHTTPRequestHandler):
    def is_admin(self) -> bool:
        return "admin=1" in self.headers.get("Cookie", "")

    def send_html(self, content: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def redirect(self, path: str, cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", path)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        return parse_qs(body, keep_blank_values=True)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        admin = self.is_admin()
        if path == "/":
            self.send_html(home_page(admin))
        elif path == "/signout":
            self.send_html(signout_page(admin))
        elif path == "/return":
            self.send_html(return_page(admin))
        elif path == "/login":
            self.send_html(login_page(admin=admin))
        elif path == "/admin":
            if not admin:
                self.redirect("/login")
            else:
                self.send_html(admin_page())
        elif path == "/logout":
            self.redirect("/", "admin=; Max-Age=0; Path=/")
        elif path == "/static/styles.css":
            css = STYLE_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(css)))
            self.end_headers()
            self.wfile.write(css)
        else:
            self.send_html(layout("Not Found", '<section class="panel"><h1>Page not found</h1></section>', admin), 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        form = self.read_form()

        if path == "/signout":
            created_at = now()
            pickup_date, return_date = safe_request_dates(
                form.get("pickup_date", [""])[0],
                form.get("return_date", [""])[0],
            )
            names = form.get("item_name", [])
            quantities = form.get("quantity", [])
            items = [
                {"name": name.strip(), "quantity": (qty.strip() or "1")}
                for name, qty in zip(names, quantities)
                if name.strip()
            ]
            records = load_records()
            records.append(
                {
                    "id": uuid4().hex,
                    "cadet": form.get("cadet", [""])[0].strip(),
                    "pickup_date": pickup_date,
                    "return_date": return_date,
                    "reason": form.get("reason", [""])[0].strip(),
                    "items": items,
                    "picked_up": False,
                    "ready_for_pickup": False,
                    "pickup_available_at": (created_at + timedelta(hours=72)).isoformat(timespec="seconds"),
                    "return_claimed": False,
                    "return_type": "",
                    "missing_items": "",
                    "returned_at": "",
                    "staff_confirmed": False,
                    "staff_confirmed_at": "",
                    "staff_issue": False,
                    "issue_details": "",
                    "issue_logged_at": "",
                    "staff_notes": "",
                    "created_at": created_at.isoformat(timespec="seconds"),
                }
            )
            save_records(records)
            self.redirect("/")
        elif path == "/return":
            records = load_records()
            record_id = form.get("record_id", [""])[0]
            for record in records:
                if record["id"] == record_id:
                    record["return_claimed"] = True
                    record["return_type"] = form.get("return_type", ["all"])[0]
                    record["missing_items"] = form.get("missing_items", [""])[0].strip()
                    record["returned_at"] = now().isoformat(timespec="seconds")
                    break
            save_records(records)
            self.redirect("/")
        elif path == "/login":
            if form.get("password", [""])[0] == ADMIN_PASSWORD:
                self.redirect("/admin", "admin=1; Path=/; SameSite=Lax")
            else:
                self.send_html(login_page("That password did not match."))
        elif path == "/admin":
            if not self.is_admin():
                self.redirect("/login")
                return
            records = load_records()
            record_id = form.get("record_id", [""])[0]
            for record in records:
                if record["id"] == record_id:
                    if form.get("action", [""])[0] == "clear_issue":
                        record["staff_issue"] = False
                        record["issue_details"] = ""
                        record["issue_logged_at"] = ""
                        break
                    was_confirmed = bool(record.get("staff_confirmed"))
                    was_issue = bool(record.get("staff_issue"))
                    record["ready_for_pickup"] = "ready_for_pickup" in form
                    record["staff_confirmed"] = "staff_confirmed" in form
                    if record["staff_confirmed"] and not was_confirmed:
                        record["staff_confirmed_at"] = now().isoformat(timespec="seconds")
                    elif not record["staff_confirmed"]:
                        record["staff_confirmed_at"] = ""

                    record["staff_issue"] = "staff_issue" in form
                    issue_details = form.get("issue_details", [""])[0].strip()
                    if record["staff_issue"]:
                        record["issue_details"] = issue_details or record.get("issue_details") or record.get("missing_items", "")
                        if not was_issue or not record.get("issue_logged_at"):
                            record["issue_logged_at"] = now().isoformat(timespec="seconds")
                    else:
                        record["issue_details"] = ""
                        record["issue_logged_at"] = ""

                    new_note = form.get("staff_notes", [""])[0].strip()
                    if new_note:
                        stamp = now().strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")
                        existing = record.get("staff_notes", "").strip()
                        addition = f"{stamp}: {new_note}"
                        record["staff_notes"] = f"{existing}; {addition}" if existing else addition
                    break
            save_records(records)
            self.redirect("/admin")
        else:
            self.redirect("/")


if __name__ == "__main__":
    if os.environ.get("RENDER"):
        HOST = "0.0.0.0"
    server = ThreadingHTTPServer((HOST, PORT), EquipmentHandler)
    print(f"Blue Tigers Equipment Store running on {HOST}:{PORT}")
    server.serve_forever()
