package ado

import (
	"context"
	"time"

	"github.com/microsoft/azure-devops-go-api/azuredevops"
	"github.com/microsoft/azure-devops-go-api/azuredevops/core"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
)

type ADO struct {
	// orgURL contains the organization URL for the ADO instance.
	orgURL string
	// pat contains the Personal Access Token for authentication with ADO.
	pat string

	// Client contains the ADO Client
	Client *core.Client
}

func NewClient(ctx context.Context, pat, url string) (*ADO, error) {
	_, span := otel.Tracer("").Start(ctx, "ado.NewClient")
	defer span.End()
	cc, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	span.AddEvent("creating ADO connection")
	span.SetAttributes(
		attribute.String("ADO URL", url),
		attribute.String("DEBUG", pat),
	)
	cn := azuredevops.NewPatConnection(url, pat)

	clt, err := core.NewClient(cc, cn)
	if err != nil {
		return nil, err
	}

	ado := ADO{
		orgURL: url,
		pat:    pat,
		Client: &clt,
	}

	// Create a connection to your organization
	return &ado, nil
}
