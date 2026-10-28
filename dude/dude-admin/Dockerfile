# syntax=docker/dockerfile:1.7
FROM golang:1.22-alpine AS builder

ARG GOPROXY=https://goproxy.cn,direct
ENV GOPROXY=${GOPROXY} \
    GOMAXPROCS=1 \
    GOMEMLIMIT=256MiB \
    GOFLAGS=-p=1

WORKDIR /app

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod,sharing=locked go mod download

COPY . .

RUN --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    --mount=type=cache,target=/root/.cache/go-build,sharing=locked \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /admin ./cmd/gateway
RUN --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    --mount=type=cache,target=/root/.cache/go-build,sharing=locked \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /healthcheck ./cmd/healthcheck

FROM scratch

WORKDIR /app
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /admin /admin
COPY --from=builder /healthcheck /healthcheck
COPY migrations/ ./migrations/
COPY static/ ./static/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/healthcheck"]

ENTRYPOINT ["/admin"]
