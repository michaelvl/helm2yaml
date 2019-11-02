#!/bin/bash

set -x
set -e

KUBECTL_IMAGE=bitnami/kubectl:1.15.0
# Pass-in both the user .kube folder and the current value of KUBECONFIG
KUBECFG="-v ${HOME}/.kube:${HOME}/.kube"
KUBECTL_CMD="docker run -ti --user $(id -u) --rm -e KUBECONFIG $KUBECFG:ro ${KUBECTL_IMAGE}"
${KUBECTL_CMD} "$@"
