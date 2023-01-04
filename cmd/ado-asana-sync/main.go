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
	"github.com/uptrace/opentelemetry-go-extra/otelzap"
	"go.opentelemetry.io/otel"
	"go.uber.org/zap"
)

type app struct {
	adoClient *ado.ADO
	logger    *otelzap.SugaredLogger
	shutdown  func(ctx context.Context) error
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

	if err = a.setupAdoClient(ctx); err != nil {
		a.logger.Ctx(ctx).Fatalw("failed to create ADO client", "error", err)
	}

	spew.Dump(a.adoClient)

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
	a.adoClient, err = ado.NewClient(ctx, adoPAT, adoURL)
	return err
}
