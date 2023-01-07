package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/danstis/ado-asana-sync/internal/ado"
	"github.com/danstis/ado-asana-sync/internal/version"
	"github.com/danstis/ado-asana-sync/pkg/logging"
	"github.com/danstis/ado-asana-sync/pkg/tracing"
	"github.com/davecgh/go-spew/spew"
	"github.com/tambet/go-asana/asana"
	"github.com/uptrace/opentelemetry-go-extra/otelzap"
	"go.opentelemetry.io/otel"
	"go.uber.org/zap"
	"golang.org/x/oauth2"
)

type app struct {
	ado      *ado.ADO
	asana    *asana.Client
	logger   *otelzap.SugaredLogger
	shutdown func(ctx context.Context) error
}

// Main entry point for the app.
func main() {
	log.Printf("ADO Asana Sync v%v", version.Version)
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	var err error

	// create the logger and initialise the tracing.
	a := &app{}
	if err = a.startup(); err != nil {
		log.Fatal(err)
	}
	defer a.shutdown(ctx) //nolint:errcheck
	defer a.logger.Sync() //nolint:errcheck

	ctx, span := otel.Tracer("").Start(ctx, "main")
	defer span.End()

	a.setupAsanaClient(ctx)

	if err = a.setupAdoClient(ctx); err != nil {
		a.logger.Ctx(ctx).Fatalw("failed to create ADO client", "error", err)
	}

	pjs, err := a.ado.GetProjects(ctx)
	if err != nil {
		a.logger.Ctx(ctx).Fatalw("failed to list ADO clients", "error", err)
	}

	wks, err := a.asana.ListWorkspaces(context.Background())
	if err != nil {
		a.logger.Ctx(ctx).Fatalw("failed to list Asana workspaces", "error", err)
	}

	spew.Dump(pjs)
	spew.Dump(wks)

	span.End()
	WaitForInterrupt()
}

// WaitForInterrupt blocks until a SIGINT, SIGTERM or another OS interrupt is received.
// "Pause until Ctrl+C", basically.
func WaitForInterrupt() {
	// Thanks to various Discord Gophers for this very simple stuff.
	signalCh := make(chan os.Signal, 1)
	signal.Notify(signalCh, syscall.SIGTERM, os.Interrupt)
	<-signalCh
}

func (a *app) startup() error {
	// Create tracer.
	var err error
	a.shutdown, err = tracing.InitTracer(version.Version)
	if err != nil {
		return err
	}

	// Init the logger, including sending logs to the tracer.
	a.logger, err = logging.InitLogger(zap.InfoLevel)
	if err != nil {
		return err
	}

	return nil
}

func (a *app) setupAdoClient(ctx context.Context) error {
	ctx, span := otel.Tracer("").Start(ctx, "setupAdoClient")
	defer span.End()

	// Read environment variables for ADO details.
	adoPAT := os.Getenv("ADO_PAT")
	adoURL := os.Getenv("ADO_URL")

	var err error
	a.ado, err = ado.NewClient(ctx, adoPAT, adoURL)
	return err
}

func (a *app) setupAsanaClient(ctx context.Context) {
	_, span := otel.Tracer("").Start(ctx, "asana.NewClient")
	defer span.End()

	token := os.Getenv("ASANA_TOKEN")

	// Use the Asana Personal Access Token.
	oc := oauth2.NewClient(ctx, oauth2.StaticTokenSource(&oauth2.Token{AccessToken: token}))
	// Init the asana client.
	a.asana = asana.NewClient(oc)
}
