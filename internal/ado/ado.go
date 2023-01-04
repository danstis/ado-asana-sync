package ado

import (
	"context"
	"time"

	"github.com/microsoft/azure-devops-go-api/azuredevops"
	"github.com/microsoft/azure-devops-go-api/azuredevops/core"
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
	cc, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	connection := azuredevops.NewPatConnection(url, pat)

	clt, err := core.NewClient(cc, connection)
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
