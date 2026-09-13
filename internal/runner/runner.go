// runner.go
package runner

import (
	"context"
	"log"
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/time/rate"

	"github.com/amirtkz/dapr-overhead-bench/internal/connector"
	"github.com/amirtkz/dapr-overhead-bench/internal/metrics"
)

// Options are the knobs shared by all connectors in a run.
type Options struct {
	Concurrency int           // workers per connector
	Rate        int           // operations/second per connector; 0 means unthrottled
	Warmup      time.Duration // period whose measurements are discarded
	OpTimeout   time.Duration // per-operation deadline, bounds a hung backend
}

// Run benchmarks every connector until ctx is cancelled, then returns.
func Run(ctx context.Context, conns []connector.Connector, opt Options) {
	// warmup runs the full workload but throws the numbers away
	if opt.Warmup > 0 {
		log.Printf("warmup: %s (measurements discarded)", opt.Warmup)

		warmCtx, cancel := context.WithTimeout(ctx, opt.Warmup)

		drive(warmCtx, conns, opt, false)

		cancel()
	}

	log.Printf("measuring: %d connectors, concurrency=%d rate=%d/s", len(conns), opt.Concurrency, opt.Rate)

	drive(ctx, conns, opt, true)
}

// drive runs every connector in parallel until ctx ends. record=false skips
// metric emission, which is what makes the warmup pass invisible in the results.
func drive(ctx context.Context, conns []connector.Connector, opt Options, record bool) {
	var wg sync.WaitGroup

	for _, c := range conns {
		wg.Add(1)

		go func(c connector.Connector) {
			defer wg.Done()
			driveConnector(ctx, c, opt, record)
		}(c)
	}

	wg.Wait()
}

func driveConnector(ctx context.Context, c connector.Connector, opt Options, record bool) {
	ops := c.Ops()

	// a token bucket paces the connector as a whole
	var limiter *rate.Limiter
	if opt.Rate > 0 {
		limiter = rate.NewLimiter(rate.Limit(opt.Rate), opt.Concurrency)
	}

	// iteration numbers
	var counter atomic.Int64

	var wg sync.WaitGroup
	for w := 0; w < opt.Concurrency; w++ {
		wg.Add(1)

		go func() {
			defer wg.Done()
			for ctx.Err() == nil {
				if limiter != nil {
					if err := limiter.Wait(ctx); err != nil {
						return // context cancelled
					}
				}

				i := int(counter.Add(1))

				// ops run in declaration order, so a "read" always follows the
				// "write" of the same key and never misses
				for _, op := range ops {
					runOnce(ctx, c, op, i, opt.OpTimeout, record)
				}
			}
		}()
	}
	wg.Wait()
}

// runOnce times exactly one operation: the timer brackets the call and nothing
// else, so the measurement is the data path and not the harness.
func runOnce(ctx context.Context, c connector.Connector, op connector.Op, i int, timeout time.Duration, record bool) {
	opCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	start := time.Now()
	err := op.Run(opCtx, i)
	elapsed := time.Since(start)

	if !record {
		return
	}

	// shutdown cancellations are not a property of the connector
	if err != nil && ctx.Err() != nil {
		return
	}

	metrics.Observe(c.Backend(), c.Mode(), op.Name, elapsed, err)
}
