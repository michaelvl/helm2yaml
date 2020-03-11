#!/bin/bash

set -x
set -e

HELM_IMAGE=alpine/helm:2.16.1
#HELM_IMAGE=alpine/helm:3.0.0

KUBECFG="-v ${HOME}/.kube/kubecfg240:/root/.kube/config"

# Note, this changes for Helm3
HELM_CFG="-v ${HOME}/.helm:/.helm"

HELM_CMD="docker run -ti --user $(id -u):$(id -g) --rm $KUBECFG:ro $HELM_CFG:rw ${HELM_IMAGE}"
${HELM_CMD} "$@"
