# Local development image built from the last public MinIO Community release.
# Pre-built Community images are no longer distributed by MinIO.
FROM golang:1.24-alpine AS build

RUN apk add --no-cache git
RUN CGO_ENABLED=0 go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

FROM alpine:3.22

RUN apk add --no-cache ca-certificates curl
COPY --from=build /go/bin/minio /usr/local/bin/minio

EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
