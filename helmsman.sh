#! /bin/bash

set -xe

mkdir -p ./rendered

# Map current folder as /src and assume all files passed with -f are relative to this
docker run --rm -v $(pwd):/src:ro -v $(pwd)/rendered:/rendered:rw michaelvl/helm2yaml --create-namespace --render-to /rendered/out.yaml helmsman $@

# Namespace is missing - 'helm template' does not add namespace
cat rendered/out.yaml | envsubst | kubectl apply -f -
