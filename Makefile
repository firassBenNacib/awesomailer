.DEFAULT_GOAL := help
.ONESHELL:
SHELL := /bin/bash

PY       ?= python3
MAILER   ?= main.py
PROJECT_DIR := $(abspath .)

CRON_BEGIN_DAILY := \# BEGIN awesomailer daily
CRON_END_DAILY   := \# END awesomailer daily
CRON_BEGIN_SPEC  := \# BEGIN awesomailer cron
CRON_END_SPEC    := \# END awesomailer cron

.PHONY: help install uninstall sample-contacts sample-contact dry-run send-now send-at daily cron report clean-logs

help:
	@printf "Usage: make <command> [args]\n\n"
	@printf "Main commands:\n"
	@printf "  install            Install dependencies\n"
	@printf "  uninstall          Uninstall dependencies listed in requirements.txt\n"
	@printf "  dry-run            Build emails without sending\n"
	@printf "  send-now           Send immediately\n"
	@printf "  send-at            Schedule one-shot at local time\n"
	@printf "  daily              Install crontab job to run daily at HH:MM\n"
	@printf "  cron               Install crontab job with a custom SPEC\n"
	@printf "  report             Rebuild dashboard\n\n"
	@printf "All other commands:\n"
	@printf "  sample-contacts    Create template contacts.csv\n"
	@printf "  clean-logs         Remove logs/*\n"
	@printf "  help               Show help\n\n"
	@printf "Environment variables use before the command\n"
	@printf "  AT=VALUE           Time for send-at (YYYY-MM-DD HH:MM) or daily (HH:MM)\n"
	@printf "  SPEC=VALUE         Cron 'm h dom mon dow' for cron\n"
	@printf "  PY=EXE             Python executable (default python3)\n"
	@printf "  MAILER=FILE        Entry script (default main.py)\n"

install:
	@$(PY) -m pip install -r requirements.txt

uninstall:
	@$(PY) -m pip uninstall -y -r requirements.txt || true

sample-contacts:
	@mkdir -p attachments/en attachments/fr attachments/es logs
	@printf "%s\n" \
	"name,email,lang,attachments,custom1" \
	"One,one@example.com,en,attachments/en/*,Custom note here" \
	"Two,two@example.fr,fr,attachments/fr/example.pdf,Note personnalisée" \
	"Three,three@example.es,es,,Nota personalizada" \
	> contacts.csv
	@echo "[ok] contacts.csv created"

sample-contact: sample-contacts

dry-run:
	@mkdir -p logs/dry-run
	@$(PY) $(MAILER) --send-now --dry-run --out-dir logs/dry-run
	@echo "[ok] previews in logs/dry-run/"

send-now:
	@$(PY) $(MAILER) --send-now

send-at:
	@test -n "$(AT)" || (echo "Set AT='YYYY-MM-DD HH:MM'"; exit 1)
	@mkdir -p logs
	@nohup bash -c 'cd "$(PROJECT_DIR)" && /usr/bin/env $(PY) "$(MAILER)" --send-at "$(AT)"' \
	  >> logs/bg-send-at.log 2>&1 & echo $$! > logs/send-at.pid
	@echo "[bg] send-at scheduled. PID: $$(cat logs/send-at.pid). Logs: logs/bg-send-at.log"

daily:
	@test -n "$(AT)" || (echo "Set AT='HH:MM'"; exit 1)
	@command -v crontab >/dev/null || (echo "crontab not found on this system"; exit 1)
	@mkdir -p logs
	@ts=$$(date +%s); crontab -l > "logs/crontab.backup-$$ts" 2>/dev/null || true
	@{ \
	  crontab -l 2>/dev/null | sed '/^$(CRON_BEGIN_DAILY)/,/^$(CRON_END_DAILY)/d'; \
	  printf "%s\n" "$(CRON_BEGIN_DAILY)"; \
	  AT_VAL="$(AT)"; hh="$${AT_VAL%%:*}"; mm="$${AT_VAL#*:}"; \
	  echo "$$mm $$hh * * * cd $(PROJECT_DIR) && /usr/bin/env flock -n logs/awesomailer.lock /usr/bin/env $(PY) $(MAILER) --send-now >> logs/cron-daily.log 2>&1"; \
	  printf "%s\n" "$(CRON_END_DAILY)"; \
	} | crontab -
	@echo "[cron] installed daily job at $(AT) (system timezone). View with: crontab -l"

cron:
	@test -n "$(SPEC)" || (echo "Set SPEC='m h dom mon dow'"; exit 1)
	@command -v crontab >/dev/null || (echo "crontab not found on this system"; exit 1)
	@mkdir -p logs
	@ts=$$(date +%s); crontab -l > "logs/crontab.backup-$$ts" 2>/dev/null || true
	@{ \
	  crontab -l 2>/dev/null | sed '/^$(CRON_BEGIN_SPEC)/,/^$(CRON_END_SPEC)/d'; \
	  printf "%s\n" "$(CRON_BEGIN_SPEC)"; \
	  echo "$(SPEC) cd $(PROJECT_DIR) && /usr/bin/env flock -n logs/awesomailer.lock /usr/bin/env $(PY) $(MAILER) --send-now >> logs/cron-spec.log 2>&1"; \
	  printf "%s\n" "$(CRON_END_SPEC)"; \
	} | crontab -
	@echo "[cron] installed SPEC '$(SPEC)' (system timezone). View with: crontab -l"

report:
	@$(PY) $(MAILER) --report

clean-logs:
	@rm -rf logs/*
