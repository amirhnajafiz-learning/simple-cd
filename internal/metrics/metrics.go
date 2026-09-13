// metrics.go
package metrics

import (
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var labels = []string{"backend", "mode", "op"}

var (
	Duration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "bench_op_duration_seconds",
		Help:    "Latency of a single benchmarked operation.",
		Buckets: []float64{.0001, .00025, .0005, .001, .0025, .005, .01, .025, .05, .1, .25, .5, 1},
	}, labels)
	Total = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "bench_ops_total",
		Help: "Number of benchmarked operations attempted.",
	}, append(append([]string{}, labels...), "status"))
	Up = prometheus.NewGaugeVec(prometheus.GaugeOpts{
		Name: "bench_connector_up",
		Help: "1 if the connector connected successfully, 0 otherwise.",
	}, []string{"backend", "mode"})
)

func init() {
	prometheus.MustRegister(Duration, Total, Up)
}

// Observe records one completed operation. err == nil is recorded as a success;
// failures are counted but their latency is still observed, since a slow failure
// is itself part of the overhead story.
func Observe(backend, mode, op string, d time.Duration, err error) {
	status := "ok"
	if err != nil {
		status = "error"
	}

	Duration.WithLabelValues(backend, mode, op).Observe(d.Seconds())
	Total.WithLabelValues(backend, mode, op, status).Inc()
}

// Serve starts the /metrics endpoint. It blocks until the server stops.
func Serve(addr string) error {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())

	// Trivial liveness endpoint so compose can gate Prometheus on the app.
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	return http.ListenAndServe(addr, mux)
}
