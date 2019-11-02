#!/bin/bash

set -x
set -e

SONOBUOY_IMAGE=sonobuoy/sonobuoy:v0.16.2
# Pass-in both the user .kube folder and the current value of KUBECONFIG
KUBECFG="-v ${HOME}/.kube:${HOME}/.kube"
# 'sonobuoy retrieve' need to write data, hence the '-w' and this bind mount
RESULT_MOUNT="-v $(pwd):/results"
SONOBUOY_CMD="docker run -ti --user $(id -u) --rm -e KUBECONFIG $KUBECFG:ro $RESULT_MOUNT:rw -w /results --entrypoint /sonobuoy $SONOBUOY_IMAGE"
${SONOBUOY_CMD} "$@"
