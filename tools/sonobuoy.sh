#!/bin/bash

set -x
set -e

SONOBUOY_IMAGE=sonobuoy/sonobuoy:v0.16.2
# Pass-in both the user .kube folder and the current value of KUBECONFIG
KUBECFG="-v ${HOME}/.kube:${HOME}/.kube"
SONOBUOY_CMD="docker run -ti --user $(id -u) --rm -e KUBECONFIG $KUBECFG:ro --entrypoint /sonobuoy ${SONOBUOY_IMAGE}"
${SONOBUOY_CMD} "$@"
