#!/bin/bash

set -x
set -e

IMAGE=michaelvl/kustomize:20200131-1549-3e89bbf-v3.5.4
MANIFESTS="-v $(pwd):/work"
docker run -ti --user $(id -u):$(id -g) --rm -w /work $MANIFESTS:ro ${IMAGE} "$@"
