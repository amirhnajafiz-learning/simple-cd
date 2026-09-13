// workload.go
package connector

import "fmt"

// Workload is the identical payload and keyspace handed to all six connectors.
// Sharing it guarantees that the only variable between two results is the data
// path, never the amount of data moved.
type Workload struct {
	Payload  []byte // value written on every operation
	Keyspace int    // keys are cycled modulo this, keeping the dataset bounded
}

// NewWorkload builds a workload with a payload of the requested size.
func NewWorkload(payloadBytes, keyspace int) Workload {
	if keyspace < 1 {
		keyspace = 1
	}
	payload := make([]byte, payloadBytes)
	for i := range payload {
		// Non-zero, non-uniform bytes so compression in any layer cannot
		// flatter one backend over another.
		payload[i] = byte('a' + i%26)
	}
	return Workload{Payload: payload, Keyspace: keyspace}
}

// Key maps an iteration number onto the bounded keyspace.
func (w Workload) Key(i int) string {
	return fmt.Sprintf("bench-key-%d", i%w.Keyspace)
}
