package tracing

import (
	"context"
	"fmt"
	"log"
	"os"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

var (
	collectorURL = os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	endpointType = os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT_TYPE")
	serviceName  = os.Getenv("OTEL_SERVICE_NAME")
)

func InitTracer(version string) (func(context.Context) error, error) {
	log.Printf("collectorURL=%q serviceName=%q", collectorURL, serviceName)
	ctx := context.Background()

	host, err := os.Hostname()
	if err != nil {
		return nil, fmt.Errorf("failed to get hostname: %w", err)
	}
	res, err := resource.New(ctx,
		resource.WithAttributes(
			// the service name used to display traces in backends
			attribute.String("service.name", serviceName),
			attribute.String("library.language", "go"),
			attribute.String("service.version", version),
			attribute.String("host.hostname", host),
			attribute.String("host.name", host),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create resource: %w", err)
	}

	traceClient, err := getClient(endpointType)
	if err != nil {
		return nil, fmt.Errorf("failed to create client: %w", err)
	}

	traceExporter, err := otlptrace.New(ctx, traceClient)
	if err != nil {
		return nil, fmt.Errorf("failed to create exporter: %w", err)
	}

	// Register the trace exporter with a TracerProvider, using a batch
	// span processor to aggregate spans before export.
	bsp := sdktrace.NewBatchSpanProcessor(traceExporter)
	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
		sdktrace.WithResource(res),
		sdktrace.WithSpanProcessor(bsp),
	)
	otel.SetTracerProvider(tracerProvider)

	// set global propagator to tracecontext (the default is no-op).
	otel.SetTextMapPropagator(propagation.TraceContext{})

	return tracerProvider.Shutdown, nil
}

func getClient(t string) (otlptrace.Client, error) {
	switch t {
	case "http":
		return otlptracehttp.NewClient(
			otlptracehttp.WithInsecure(),
			otlptracehttp.WithEndpoint(collectorURL),
		), nil
	case "grpc":
		return otlptracegrpc.NewClient(
			otlptracegrpc.WithInsecure(),
			otlptracegrpc.WithEndpoint(collectorURL),
		), nil
	default:
		return nil, fmt.Errorf("unknown endpoint type: %q", t)
	}
}
