import os, csv, ssl, time, argparse, mimetypes, logging, glob, re
from datetime import datetime
from zoneinfo import ZoneInfo
from string import Template
import smtplib
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
from typing import cast, Optional, List, Dict, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

SMTP_HOST      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", "465"))
SENDER_EMAIL   = os.environ.get("SENDER_EMAIL")
SENDER_NAME    = os.environ.get("SENDER_NAME", "Bot")
APP_PASSWORD   = os.environ.get("APP_PASSWORD")

TEMPLATE_ROOT  = os.environ.get("TEMPLATE_ROOT", "templates")
CONTACTS_CSV   = os.environ.get("CONTACTS_CSV", "contacts.csv")

SLEEP_BETWEEN  = float(os.environ.get("SLEEP_SECONDS", "8"))
DEFAULT_TZ     = os.environ.get("TZ_NAME", "Africa/Tunis")

LOG_DIR        = os.environ.get("LOG_DIR", "logs")
LOG_FILE       = os.path.join(LOG_DIR, "mailer.log")
SENT_CSV       = os.path.join(LOG_DIR, "sent.csv")
DASHBOARD_HTML = os.path.join(LOG_DIR, "dashboard.html")

ATTACH_LANG_DIR_FALLBACK = os.environ.get("ATTACH_LANG_DIR", "1") == "1"

DEFAULTS: Dict[str, str] = {
    "from_name": os.environ.get("FROM_NAME", SENDER_NAME),
    "from_email": os.environ.get("FROM_EMAIL", SENDER_EMAIL or ""),
    "reply_to": os.environ.get("REPLY_TO", SENDER_EMAIL or ""),
}

def setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("mailer")
    logger.setLevel(logging.INFO)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    sh = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt); sh.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(fh); logger.addHandler(sh)
    return logger

LOGGER = setup_logging()

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def render(text: str, mapping: Dict[str, str]) -> str:
    return Template(text).safe_substitute(mapping)

def load_templates(lang: str, row: Dict[str, str]) -> Tuple[str, str, Optional[str], str]:
    lang = (lang or "en").strip().lower()
    lang_dir = os.path.join(TEMPLATE_ROOT, lang)
    subj_path = (row.get("subject_file") or os.path.join(lang_dir, "subject.txt")).strip()
    body_txt  = (row.get("body_file")    or os.path.join(lang_dir, "body.txt")).strip()
    body_html = (row.get("body_html_file") or os.path.join(lang_dir, "body.html")).strip()
    if not os.path.isfile(subj_path):
        raise FileNotFoundError(f"Missing subject template: {subj_path}")
    if not os.path.isfile(body_txt):
        raise FileNotFoundError(f"Missing body template: {body_txt}")
    subject_text = read_text(subj_path)
    body_text    = read_text(body_txt)
    html_text: Optional[str] = None
    if os.path.isfile(body_html):
        candidate = read_text(body_html).strip()
        if candidate:
            html_text = candidate
    return subject_text, body_text, html_text, lang

def attach_file(msg: EmailMessage, path: str) -> None:
    ctype, encoding = mimetypes.guess_type(path)
    if ctype is None or encoding is not None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    with open(path, "rb") as f:
        msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(path))

def expand_attachments(value: str) -> List[str]:
    if not value:
        return []
    parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    files: List[str] = []
    for pat in parts:
        matches = sorted(glob.glob(pat))
        if matches:
            files.extend(m for m in matches if os.path.isfile(m))
        else:
            LOGGER.warning(f"[ATTACH] pattern matched nothing: {pat}")
    uniq: List[str] = []
    seen = set()
    for f in files:
        if f not in seen:
            uniq.append(f)
            seen.add(f)
    return uniq

def read_sent_index() -> Dict[str, Dict[str, str]]:
    idx: Dict[str, Dict[str, str]] = {}
    if os.path.isfile(SENT_CSV):
        with open(SENT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                idx[(row.get("email") or "").strip()] = row
    return idx

def append_sent_record(row: Dict[str, str], subject: str, status: str, error: str = "") -> None:
    exists = os.path.isfile(SENT_CSV)
    with open(SENT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time","email","name","lang","subject","status","error"])
        if not exists:
            w.writeheader()
        w.writerow({
            "time": datetime.now().isoformat(timespec="seconds"),
            "email": (row.get("email") or "").strip(),
            "name": (row.get("name") or "").strip(),
            "lang": (row.get("lang") or "").strip(),
            "subject": subject,
            "status": status,
            "error": error
        })

def generate_dashboard(contacts_rows: List[Dict[str, str]], sent_idx: Dict[str, Dict[str, str]]) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    total = len(contacts_rows)
    sent_count = sum(1 for r in contacts_rows if sent_idx.get((r.get("email") or "").strip(), {}).get("status") == "success")
    def row_html(r: Dict[str, str]) -> str:
        email = (r.get("email") or "").strip()
        srec  = sent_idx.get(email)
        checked = "checked" if srec and srec.get("status") == "success" else ""
        last = srec.get("time") if srec else ""
        subj = srec.get("subject","") if srec else ""
        name = (r.get("name") or "")
        lang = (r.get("lang") or "")
        return f"<tr><td>{name}</td><td>{email}</td><td>{lang}</td><td><input type='checkbox' {checked} disabled></td><td>{last}</td><td>{subj}</td></tr>"
    rows_html = "\n".join(row_html(r) for r in contacts_rows)
    html = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><title>Mailer Dashboard</title>
<style>
body{{font-family:Arial,sans-serif;margin:24px}} h1{{margin-bottom:0}}
.summary{{color:#444;margin:4px 0 16px}} table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px;font-size:14px}} th{{background:#f3f4f6;text-align:left}}
tr:nth-child(even){{background:#fafafa}} .badge{{display:inline-block;padding:2px 6px;background:#eef;border-radius:4px}}
</style></head><body>
<h1>Mailer Dashboard</h1>
<div class="summary">Total: <span class="badge">{total}</span> &nbsp; Sent: <span class="badge">{sent_count}</span> &nbsp; Unsent: <span class="badge">{total-sent_count}</span></div>
<table><thead><tr><th>Name</th><th>Email</th><th>Lang</th><th>Sent</th><th>Last sent</th><th>Subject</th></tr></thead><tbody>
{rows_html}
</tbody></table></body></html>"""
    with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    LOGGER.info(f"Dashboard written to {DASHBOARD_HTML}")

def build_message(row: Dict[str, str]) -> Tuple[EmailMessage, str, List[str]]:
    lang = (row.get("lang") or "en").strip().lower()
    to_addr = (row.get("email") or "").strip()
    if not to_addr or "@" not in to_addr:
        raise ValueError(f"Invalid recipient: {to_addr}")
    subject_tpl, body_txt, body_html, lang = load_templates(lang, row)
    mapping = {**DEFAULTS, **{k: (v or "") for k, v in row.items()}}
    subject = render(subject_tpl, mapping).strip().replace("\n", " ")
    body_text = render(body_txt, mapping)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = f'{SENDER_NAME} <{SENDER_EMAIL}>'
    msg["To"]      = to_addr
    if row.get("cc"):
        msg["Cc"] = row["cc"]
    if row.get("bcc"):
        msg["Bcc"] = row["bcc"]
    if DEFAULTS.get("reply_to"):
        msg["Reply-To"] = DEFAULTS["reply_to"]
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(render(body_html, mapping), subtype="html")
    files = expand_attachments(row.get("attachments", ""))
    if not files and ATTACH_LANG_DIR_FALLBACK:
        lang_dir = os.path.join("attachments", lang)
        if os.path.isdir(lang_dir):
            files = sorted([p for p in glob.glob(os.path.join(lang_dir, "*")) if os.path.isfile(p)])
    for path in files:
        try:
            attach_file(msg, path)
        except Exception as e:
            LOGGER.warning(f"[ATTACH-ERR] {path}: {e}")
    recipients: List[str] = [to_addr]
    if row.get("cc"):
        recipients += [a.strip() for a in row["cc"].replace(";", ",").split(",") if a.strip()]
    if row.get("bcc"):
        recipients += [a.strip() for a in row["bcc"].replace(";", ",").split(",") if a.strip()]
        try:
            del msg["Bcc"]
        except Exception:
            pass
    return msg, subject, recipients

def read_contacts() -> List[Dict[str, str]]:
    with open(CONTACTS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:120]

def _extract_bodies(msg: EmailMessage) -> Tuple[str, Optional[str]]:
    plain = ""
    html: Optional[str] = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                plain = part.get_content()
            elif ctype == "text/html":
                html = part.get_content()
    else:
        plain = msg.get_content()
    return plain, html

def send_batch(dry_run: bool = False, resend: bool = False, limit: Optional[int] = None, preview_dir: Optional[str] = None) -> None:
    missing = [k for k in ("SENDER_EMAIL","APP_PASSWORD") if not os.environ.get(k)]
    if missing and not dry_run:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    rows = read_contacts()
    sent_idx = read_sent_index()
    already_sent = {e for e, rec in sent_idx.items() if rec.get("status") == "success"}
    if dry_run:
        out_dir = preview_dir or os.path.join(LOG_DIR, "dry-run")
        os.makedirs(out_dir, exist_ok=True)
        i = 0
        for r in rows:
            email = (r.get("email") or "").strip()
            if not email or "@" not in email:
                print(f"[DRY-ERR] {email}: invalid recipient")
                continue
            if not resend and email in already_sent:
                print(f"[DRY-SKIP] {email} already sent")
                continue
            try:
                m, subject, _recips = build_message(r)
                plain, html = _extract_bodies(m)
                localpart = email.split("@", 1)[0]
                dest_dir = os.path.join(out_dir, _sanitize(localpart))
                os.makedirs(dest_dir, exist_ok=True)
                prefix = f"{i+1:03d}"
                subj_path = os.path.join(dest_dir, f"{prefix}.subject.txt")
                body_path = os.path.join(dest_dir, f"{prefix}.body.txt")
                with open(subj_path, "w", encoding="utf-8") as f:
                    f.write(subject + "\n")
                with open(body_path, "w", encoding="utf-8") as f:
                    f.write(plain)
                if html:
                    html_path = os.path.join(dest_dir, f"{prefix}.body.html")
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(html)
                print(f"[DRY] {m['To']} | {subject} -> {body_path}")
                i += 1
            except Exception as e:
                print(f"[DRY-ERR] {email}: {e}")
        generate_dashboard(rows, read_sent_index())
        return
    context = ssl.create_default_context()
    sender = cast(str, SENDER_EMAIL)
    password = cast(str, APP_PASSWORD)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(sender, password)
        sent = 0
        for row in rows:
            to_addr = (row.get("email") or "").strip()
            if not to_addr or "@" not in to_addr:
                LOGGER.warning(f"[SKIP] invalid email: {to_addr}")
                continue
            if not resend and to_addr in already_sent:
                LOGGER.info(f"[SKIP] already sent to {to_addr}")
                continue
            subject = ""
            try:
                msg, subject, recipients = build_message(row)
                server.send_message(msg, from_addr=SENDER_EMAIL, to_addrs=recipients)
                sent += 1
                LOGGER.info(f"[OK] {to_addr} | {subject}")
                append_sent_record(row, subject, "success")
                time.sleep(SLEEP_BETWEEN)
                if limit is not None and sent >= limit:
                    LOGGER.info(f"[STOP] limit {limit} reached")
                    break
            except Exception as e:
                LOGGER.error(f"[ERR] {to_addr}: {e}")
                append_sent_record(row, subject, "failed", str(e))
        LOGGER.info(f"[DONE] {sent} messages sent.")
    generate_dashboard(rows, read_sent_index())

def main() -> None:
    parser = argparse.ArgumentParser(description="Generic multilingual scheduled mail-merge")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--send-now", action="store_true", help="send immediately")
    g.add_argument("--send-at", type=str, help="one-shot at local time, e.g. '2025-09-13 19:00'")
    g.add_argument("--daily", type=str, help="HH:MM daily in local tz, e.g. '19:00'")
    g.add_argument("--cron", type=str, help="cron 'm h dom mon dow' in local tz")
    g.add_argument("--report", action="store_true", help="generate dashboard only")
    parser.add_argument("--tz", default=DEFAULT_TZ, help="IANA timezone name, default Africa/Tunis")
    parser.add_argument("--dry-run", action="store_true", help="build messages but do not send")
    parser.add_argument("--resend", action="store_true", help="ignore sent registry and send again")
    parser.add_argument("--limit", type=int, default=None, help="max emails to send this run")
    parser.add_argument("--out-dir", type=str, default=None, help="directory to write dry-run previews")
    args = parser.parse_args()
    if args.report:
        rows = read_contacts()
        generate_dashboard(rows, read_sent_index())
        return
    if args.send_now:
        send_batch(dry_run=args.dry_run, resend=args.resend, limit=args.limit, preview_dir=args.out_dir)
        return
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.cron import CronTrigger
    sched = BlockingScheduler(timezone=ZoneInfo(args.tz), job_defaults={"misfire_grace_time": 300, "coalesce": True})
    if args.send_at:
        dt = datetime.strptime(args.send_at, "%Y-%m-%d %H:%M")
        sched.add_job(
            send_batch,
            DateTrigger(run_date=dt.replace(tzinfo=ZoneInfo(args.tz))),
            kwargs={"dry_run": args.dry_run, "resend": args.resend, "limit": args.limit, "preview_dir": args.out_dir},
        )
        LOGGER.info(f"[SCHED] one-shot at {dt} {args.tz}")
    elif args.daily:
        hh, mm = args.daily.split(":")
        sched.add_job(
            send_batch,
            CronTrigger(hour=int(hh), minute=int(mm)),
            kwargs={"dry_run": args.dry_run, "resend": args.resend, "limit": args.limit, "preview_dir": args.out_dir},
        )
        LOGGER.info(f"[SCHED] daily at {hh}:{mm} {args.tz}")
    elif args.cron:
        m, h, dom, mon, dow = args.cron.strip().split()
        sched.add_job(
            send_batch,
            CronTrigger(minute=m, hour=h, day=dom, month=mon, day_of_week=dow),
            kwargs={"dry_run": args.dry_run, "resend": args.resend, "limit": args.limit, "preview_dir": args.out_dir},
        )
        LOGGER.info(f"[SCHED] cron {args.cron} {args.tz}")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("[EXIT] scheduler stopped")

if __name__ == "__main__":
    main()
