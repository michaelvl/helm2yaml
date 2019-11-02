#!/bin/bash

set -x
set -e

HELM_IMAGE=alpine/helm:2.15.2
KUBECFG="-v ${HOME}/.kube/kubecfg240:/root/.kube/config"
HELM_CMD="docker run -ti --rm $KUBECFG:ro ${HELM_IMAGE}"
${HELM_CMD} "$@"
