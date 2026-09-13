// main.go
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/amirtkz/dapr-overhead-bench/internal/config"
	"github.com/amirtkz/dapr-overhead-bench/internal/connector"
	"github.com/amirtkz/dapr-overhead-bench/internal/metrics"
	"github.com/amirtkz/dapr-overhead-bench/internal/runner"
)

func initVars() {
	log.SetFlags(log.LstdFlags | log.Lmsgprefix)
	log.SetPrefix("[cmd-bench] ")
}

func main() {
	// load configs
	cfg := config.Load()

	// build a new workload instance
	workload := connector.NewWorkload(cfg.PayloadBytes, cfg.Keyspace)

	// stop handlers ends the run cleanly, letting connectors close
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if cfg.Duration > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, cfg.Duration)
		defer cancel()
	}

	// the exporter comes up before any connecting happens, so Prometheus can
	// scrape bench_connector_up even when a backend is unreachable
	go func() {
		log.Printf("metrics exporter listening on %s/metrics", cfg.MetricsAddr)

		if err := metrics.Serve(cfg.MetricsAddr); err != nil {
			log.Fatalf("metrics exporter stopped: %v", err)
		}
	}()

	// data paths under comparison, paired backend by backend
	candidates := []connector.Connector{
		connector.NewNATSDirect(cfg.NATSURL, workload),
		connector.NewNATSDapr(cfg.DaprGRPCPort, cfg.DaprPubsubNATS, workload),
		connector.NewPostgresDirect(cfg.PostgresDSN, workload),
		connector.NewPostgresDapr(cfg.DaprGRPCPort, cfg.DaprStatePG, workload),
		connector.NewRedisDirect(cfg.RedisAddr, workload),
		connector.NewRedisDapr(cfg.DaprGRPCPort, cfg.DaprStateRedis, workload),
	}

	// connect candidates
	connected := connect(ctx, candidates)
	if len(connected) == 0 {
		log.Fatal("no connector could be established; check the backing services")
	}
	defer func() {
		for _, c := range connected {
			// close connection when terminated
			if err := c.Close(); err != nil {
				log.Printf("close %s: %v", connector.Name(c), err)
			}
		}
	}()

	// create a runner instance and execute workloads
	runner.Run(ctx, connected, runner.Options{
		Concurrency: cfg.Concurrency,
		Rate:        cfg.Rate,
		Warmup:      cfg.Warmup,
		OpTimeout:   5 * time.Second,
	})

	log.Print("run finished; metrics remain available until the process exits")

	// hold the exporter open briefly so a final scrape can pick up the results
	// of a fixed-duration run before the container disappears
	if cfg.Duration > 0 {
		time.Sleep(30 * time.Second)
	}
}

// connect brings up each connector, retrying to absorb the slow start of the
// backends and the sidecar. A connector that never comes up is reported as down
// and skipped rather than aborting the whole comparison.
func connect(ctx context.Context, candidates []connector.Connector) []connector.Connector {
	const attempts = 10

	var connected []connector.Connector
	for _, c := range candidates {
		name := connector.Name(c)
		var err error
		for attempt := 1; attempt <= attempts; attempt++ {
			if err = c.Connect(ctx); err == nil {
				break
			}

			log.Printf("connect %s (attempt %d/%d): %v", name, attempt, attempts, err)

			select {
			case <-ctx.Done():
				return connected
			case <-time.After(2 * time.Second):
			}
		}

		if err != nil {
			log.Printf("giving up on %s: %v", name, err)
			metrics.Up.WithLabelValues(c.Backend(), c.Mode()).Set(0)
			continue
		}

		log.Printf("connected %s", name)
		metrics.Up.WithLabelValues(c.Backend(), c.Mode()).Set(1)
		connected = append(connected, c)
	}

	return connected
}
