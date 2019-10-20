#! /bin/bash

#HELM2YAML='michaelvl/helm2yaml'
HELM2YAML='helm2yaml'

set -xe

mkdir -p ./rendered

# Map current folder as /src and assume all files passed with -f are relative to this
docker run --rm -v $(pwd):/src:ro -v $(pwd)/rendered:/rendered:rw $HELM2YAML --api-versions apiregistration.k8s.io/v1beta1 --api-versions apiextensions.k8s.io/v1beta1 --render-to /rendered/out.yaml --render-namespace-to /rendered/ns.yaml helmsman $@

kubectl apply -f rendered/ns.yaml
NS=$(yq -r '.metadata.name' rendered/ns.yaml)

# The environment variables shown here are usefull for deployment of e.g. https://github.com/MichaelVL/kubernetes-infra-cloudimg
cat rendered/out.yaml | docker run -i --entrypoint /bin/k8envsubst.py -e GRAFANA_ADMIN_PASSWD -e DNS_DOMAIN -e NFS_STORAGE_PROVISIONER_HOSTNAME $HELM2YAML | kubectl -n $NS apply -f -
