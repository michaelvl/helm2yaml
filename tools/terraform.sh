#!/bin/bash

set -x
set -e

TERRAFORM_IMAGE=hashicorp/terraform:0.12.3
TERRAFORM_CMD="docker run -ti --user $(id -u):$(id -g) --rm -w /app -v `pwd`:/app ${TERRAFORM_IMAGE}"
${TERRAFORM_CMD} "$@"
