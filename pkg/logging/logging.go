// Logging provides a logger with zap and otel integration.
// https://github.com/uptrace/opentelemetry-go-extra/tree/otelzap/v0.1.15/otelzap
package logging

import (
	"fmt"

	"github.com/uptrace/opentelemetry-go-extra/otelzap"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// InitLogger creates the new zap logger for sending telemetry while logging.
//
// configType defines the type of logger to create, either development or production.
// defaults to production.
func InitLogger(minLevel zapcore.Level) (*otelzap.SugaredLogger, error) {
	lc := zap.NewProductionConfig()
	lc.EncoderConfig.TimeKey = "timestamp"
	lc.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	l, err := lc.Build()
	if err != nil {
		return nil, fmt.Errorf("error starting logger: %w", err)
	}
	return otelzap.New(l, otelzap.WithMinLevel(zap.InfoLevel)).Sugar(), err
}
