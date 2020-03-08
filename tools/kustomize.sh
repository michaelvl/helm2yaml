#!/bin/bash

#set -x
set -e

IMAGE=michaelvl/kustomize:20200308-1332-de963de-v3.5.4
MANIFESTS="-v $(pwd):/work"
docker run -i --user $(id -u):$(id -g) --rm -w /work $MANIFESTS:ro ${IMAGE} "$@"
