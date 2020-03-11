#!/bin/bash

set -x
set -e

KUBEAUDIT_IMAGE=michaelvl/kubeaudit:0.7.0
# Pass-in both the user .kube folder and the current value of KUBECONFIG
KUBECFG="-v $(pwd)/.kube:${HOME}/.kube"
MANIFESTS="-v $(pwd):/work"
KUBEAUDIT_CMD="docker run --user $(id -u):$(id -g) --rm -e KUBECONFIG $KUBECFG:ro $MANIFESTS:ro ${KUBEAUDIT_IMAGE}"
${KUBEAUDIT_CMD} "$@"
