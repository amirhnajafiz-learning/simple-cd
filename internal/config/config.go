// config.go
package config

import (
	"os"
	"strconv"
	"time"
)

// Config is the full set of knobs for a benchmark run.
type Config struct {
	// Endpoints of the backing services
	NATSURL     string
	RedisAddr   string
	PostgresDSN string

	// Dapr sidecar endpoints
	DaprGRPCPort   string
	DaprPubsubNATS string
	DaprStateRedis string
	DaprStatePG    string

	// Workload shape
	PayloadBytes int           // size of the value written on each operation
	Keyspace     int           // number of distinct keys cycled through
	Concurrency  int           // in-flight operations per connector
	Rate         int           // target operations/second per connector (0 = unthrottled)
	Warmup       time.Duration // discarded period, lets pools and the sidecar settle
	Duration     time.Duration // total run length (0 = run until terminated)

	// Prometheus exporter
	MetricsAddr string
}

// Load reads the configuration from the environment, falling back to values
// that work with the provided docker compose stack.
func Load() Config {
	return Config{
		NATSURL:     env("NATS_URL", "nats://nats:4222"),
		RedisAddr:   env("REDIS_ADDR", "redis:6379"),
		PostgresDSN: env("POSTGRES_DSN", "postgres://bench:bench@postgres:5432/bench?sslmode=disable"),

		DaprGRPCPort:   env("DAPR_GRPC_PORT", "50001"),
		DaprPubsubNATS: env("DAPR_PUBSUB_NATS", "pubsub-nats"),
		DaprStateRedis: env("DAPR_STATE_REDIS", "statestore-redis"),
		DaprStatePG:    env("DAPR_STATE_POSTGRES", "statestore-postgres"),

		PayloadBytes: envInt("PAYLOAD_BYTES", 256),
		Keyspace:     envInt("KEYSPACE", 1000),
		Concurrency:  envInt("CONCURRENCY", 8),
		Rate:         envInt("RATE", 200),
		Warmup:       envDuration("WARMUP", 5*time.Second),
		Duration:     envDuration("DURATION", 0),

		MetricsAddr: env("METRICS_ADDR", ":9100"),
	}
}

func env(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	if v, err := strconv.Atoi(env(key, "")); err == nil {
		return v
	}
	return fallback
}

func envDuration(key string, fallback time.Duration) time.Duration {
	if v, err := time.ParseDuration(env(key, "")); err == nil {
		return v
	}
	return fallback
}
