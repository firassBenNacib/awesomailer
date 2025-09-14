
# Awesomailer

Simple mail-merge sender for Python. It builds multilingual emails from templates. It supports per-recipient variables, optional attachments, previews, and scheduling.

* [Requirements](#requirements)
* [Install](#install)
* [Configure](#configure)
* [Prepare templates and contacts](#prepare-templates-and-contacts)
* [Quick start](#quick-start)
* [Scheduling](#scheduling)
* [Attachments](#attachments)
* [CSV format](#csv-format)
* [Templates and placeholders](#templates-and-placeholders)
* [Logs and dashboard](#logs-and-dashboard)
* [CLI options](#cli-options)
* [Make targets](#make-targets)
* [Uninstall and cleanup](#uninstall-and-cleanup)
* [License](#license)
* [Author](#author)


## Requirements

* Python 3.9 or newer
* pip
* A mailbox you control (Gmail works with an App Password)
* A Unix-like shell for `make`, `nohup`, `crontab`, and `flock`

## Install

```bash
git clone https://github.com/firassBenNacib/awesomailer.git
cd awesomailer

# optional
python3 -m venv .venv
source .venv/bin/activate

make install
````

## Configure

1. Copy the example file and edit it.

   ```bash
   cp .env.example .env
   ```
2. Set:

   * `SENDER_EMAIL`
   * `APP_PASSWORD`
   * Optional: `SENDER_NAME`, `TZ_NAME`, `SLEEP_SECONDS`, `ATTACH_LANG_DIR`

`.env.example` lists every supported variable with defaults.

## Prepare templates and contacts

Directory layout:

```
templates/
  en/
    subject.txt
    body.txt
    body.html        # optional
  fr/
    subject.txt
    body.txt
    body.html
  es/
    subject.txt
    body.txt
    body.html
attachments/
  en/ ...
  fr/ ...
  es/ ...
contacts.csv
```

Create a starter CSV with examples (three attachment styles):

```bash
make sample-contacts
```

It adds:

* Row 1: all files in a folder (`attachments/en/*`)
* Row 2: a single file (`attachments/fr/example.pdf`)
* Row 3: no files (empty field)

## Quick start

Preview everything without sending.

```bash
make dry-run
```

Send now:

```bash
make send-now
```

View the dashboard:

```bash
make report
xdg-open logs/dashboard.html   # or open it in your browser
```

## Scheduling

You can run a one time job, a daily job, or any cron spec. The Makefile wraps `crontab` and keeps your other entries. It also uses `flock` to prevent overlapping runs.

### One time at a local time

```bash
AT="2025-09-15 19:00" make send-at
```

### Daily at HH\:MM

```bash
AT="19:00" make daily
```

### Custom cron spec

```bash
make cron SPEC="*/15 * * * *"
```

Remove the managed entries later:

```bash
# daily block
crontab -l | sed '/^# BEGIN awesomailer daily/,/^# END awesomailer daily/d' | crontab -

# cron block
crontab -l | sed '/^# BEGIN awesomailer cron/,/^# END awesomailer cron/d' | crontab -
```

## Attachments

Use the `attachments` column in `contacts.csv`.

* One file:

  ```
  attachments/fr/example.pdf
  ```
* Many files with commas:

  ```
  attachments/en/file1.pdf,attachments/en/file2.pdf
  ```
* Glob patterns:

  ```
  attachments/en/*
  ```

If `attachments` is empty and `ATTACH_LANG_DIR="1"`, the app attaches all files from `attachments/<lang>/` automatically.

## CSV format

Required columns:

* `name`
* `email`
* `lang`

Optional columns:

* `attachments`
* `cc`, `bcc`
* `subject_file`, `body_file`, `body_html_file` to override template paths per row
* Any other column becomes a template variable (for example `custom1`)

Example:

```csv
name,email,lang,attachments,custom1
Team One,one@example.com,en,"attachments/en/a.pdf,attachments/en/b.pdf",Custom note
Two,two@example.fr,fr,attachments/fr/example.pdf,Note personnalisée
Three,three@example.es,es,,Nota personalizada
```

## Templates and placeholders

Templates use `$variable` placeholders from:

* Defaults: `from_name`, `from_email`, `reply_to`
* CSV columns: `name`, `custom1`, etc.

Example `templates/en/subject.txt`:

```
Message for $name from $from_name
```

Example `templates/en/body.txt`:

```
Hi $name,

This is a message. You can reply directly.

$custom1

Best regards,
$from_name
```

You can also add `body.html`. The app sends a plain text part and, when present, an HTML part.

## Logs and dashboard

* `logs/mailer.log`: run log
* `logs/sent.csv`: send history
* `logs/dashboard.html`: simple report UI
* `logs/dry-run/<localpart>/`: previews created by `make dry-run`
* `logs/bg-send-at.log`: background one time run
* `logs/cron-daily.log`, `logs/cron-spec.log`: crontab runs

## CLI options

You can also run the app directly:

```bash
python3 main.py --send-now [--dry-run] [--resend] [--limit N] [--tz Zone] [--out-dir path]
python3 main.py --send-at "YYYY-MM-DD HH:MM" [--tz Zone] [...]
python3 main.py --daily "HH:MM" [--tz Zone] [...]
python3 main.py --cron "m h dom mon dow" [--tz Zone] [...]
python3 main.py --report
```

Flags:

* `--dry-run`: build messages without sending
* `--resend`: ignore `sent.csv` and send again
* `--limit N`: stop after N messages
* `--tz Zone`: IANA zone, defaults to `TZ_NAME`
* `--out-dir path`: where to write dry-run previews

Scheduler defaults:

* Time zone from `--tz` or `TZ_NAME`
* Misfire grace time 300 seconds
* Coalescing on (missed runs collapse into one)

## Make targets

```text
install         Install dependencies
uninstall       Uninstall dependencies listed in requirements.txt
dry-run         Build emails without sending, write previews to logs/dry-run
send-now        Send immediately
send-at         Schedule one time at local time (env AT="YYYY-MM-DD HH:MM")
daily           Install a daily crontab job (env AT="HH:MM")
cron            Install a custom cron job (env SPEC="m h dom mon dow")
report          Rebuild the dashboard
sample-contacts Create a sample contacts.csv with attachment examples
clean-logs      Remove files in logs/
help            Show help
```

Environment with `make`:

* `AT="..."`, `SPEC="..."`, `PY="python3"`, `MAILER="main.py"`

## Uninstall and cleanup

```bash
make uninstall
make clean-logs
# optional: remove crontab blocks using the sed commands in the Scheduling section
```

## License

This project is licensed under the [MIT License](./LICENSE).

## Author

Created and maintained by [Firas Ben Nacib](https://github.com/firassBenNacib) - [bennacibfiras@gmail.com](mailto:bennacibfiras@gmail.com)

