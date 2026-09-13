// dapr.go
package connector

import (
	"context"
	"fmt"

	dapr "github.com/dapr/go-sdk/client"
)

// daprBase is the shared plumbing of the three Dapr connectors.
type daprBase struct {
	grpcPort string
	client   dapr.Client
}

func (d *daprBase) connect(_ context.Context) error {
	c, err := dapr.NewClientWithPort(d.grpcPort)
	if err != nil {
		return fmt.Errorf("dial dapr sidecar on port %s: %w", d.grpcPort, err)
	}

	d.client = c

	return nil
}

func (d *daprBase) Mode() string { return ModeDapr }

func (d *daprBase) Close() error {
	if d.client != nil {
		d.client.Close()
	}

	return nil
}
