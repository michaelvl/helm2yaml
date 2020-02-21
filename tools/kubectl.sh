#!/bin/bash

set -x
set -e

KUBECTL_IMAGE=bitnami/kubectl:1.17.3
# Pass-in both the user .kube folder and the current value of KUBECONFIG
KUBECFG="-v ${HOME}/.kube:${HOME}/.kube"
MANIFESTS="-v $(pwd):/work"
KUBECTL_CMD="docker run -ti --user $(id -u):$(id -g) --net host --rm -e KUBECONFIG $KUBECFG:ro -w /work $MANIFESTS:ro ${KUBECTL_IMAGE}"
${KUBECTL_CMD} "$@"
