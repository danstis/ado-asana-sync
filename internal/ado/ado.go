package ado

import (
	"context"
	"time"

	"github.com/microsoft/azure-devops-go-api/azuredevops"
	"github.com/microsoft/azure-devops-go-api/azuredevops/core"
	"go.opentelemetry.io/otel"
)

type ADO struct {
	// orgURL contains the organization URL for the ADO instance.
	orgURL string
	// pat contains the Personal Access Token for authentication with ADO.
	pat string

	// Client contains the ADO Client
	Client core.Client
}

func NewClient(ctx context.Context, pat, url string) (*ADO, error) {
	_, span := otel.Tracer("").Start(ctx, "ado.NewClient")
	defer span.End()
	cc, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	span.AddEvent("creating ADO connection")
	cn := azuredevops.NewPatConnection(url, pat)

	clt, err := core.NewClient(cc, cn)
	if err != nil {
		return nil, err
	}

	ado := ADO{
		orgURL: url,
		pat:    pat,
		Client: clt,
	}

	// Create a connection to your organization
	return &ado, nil
}

func (ado *ADO) GetProjects(ctx context.Context) ([]string, error) {
	_, span := otel.Tracer("").Start(ctx, "ado.GetProjects")
	defer span.End()
	var projects []string
	// Get first page of projects.
	resp, err := ado.Client.GetProjects(ctx, core.GetProjectsArgs{})
	if err != nil {
		return nil, err
	}
	i := 0
	for resp != nil {
		// Log the page of team project names
		for _, v := range (*resp).Value {
			projects = append(projects, *v.Name)
			i++
		}

		// if continuationToken has a value, then there is at least one more page of projects to get
		if resp.ContinuationToken != "" {
			// Get next page of team projects
			projectArgs := core.GetProjectsArgs{
				ContinuationToken: &resp.ContinuationToken,
			}
			resp, err = ado.Client.GetProjects(ctx, projectArgs)
			if err != nil {
				return projects, err
			}
		} else {
			resp = nil
		}
	}
	return projects, nil
}
