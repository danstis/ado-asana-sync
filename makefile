VERSION:=$(shell gitversion /output json /showvariable FullSemVer)
include ./deploy/.env
export
run:
	go run -ldflags "-s -w -X 'github.com/danstis/ado-asana-sync/internal/version.Version=$(VERSION)'" ./cmd/ado-asana-sync

up:
	docker compose --project-directory deploy up --build --remove-orphans

upd:
	docker compose --project-directory deploy up -d --build --remove-orphans

down:
	docker compose --project-directory deploy down

version:
	@echo $(VERSION)
