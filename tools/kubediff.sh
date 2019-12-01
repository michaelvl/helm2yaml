#!/bin/bash

set -x
set -e

KUBEDIFF_IMAGE=weaveworks/kubediff:master-385f72f
# Pass-in both the user .kube folder and the current value of KUBECONFIG
KUBECFG="-v ${HOME}/.kube:${HOME}/.kube"
MANIFESTS="-v $(pwd):/work"
KUBECTL_CMD="docker run -ti --rm --entrypoint /kubediff -e KUBECONFIG $KUBECFG:ro $MANIFESTS:ro ${KUBEDIFF_IMAGE}"
${KUBECTL_CMD} "$@"
