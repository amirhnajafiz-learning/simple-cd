# Build stage: compile a static binary so the runtime image stays tiny.
FROM golang:1.26 AS build
WORKDIR /src

# Dependencies first, so source edits do not invalidate the module cache layer.
COPY go.mod go.sum ./
RUN go mod download

COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -o /bench ./cmd/bench

# Runtime stage.
FROM alpine:3.20
RUN adduser -D -u 10001 bench
COPY --from=build /bench /usr/local/bin/bench
USER bench
EXPOSE 9100
ENTRYPOINT ["/usr/local/bin/bench"]
