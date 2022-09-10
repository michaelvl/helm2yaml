FROM python:3.7.4-slim-stretch

ARG HELM_VERSION="v3.9.4"
ENV HELM_VERSION=$HELM_VERSION

RUN apt-get -y update && apt-get install -y curl && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ADD requirements.txt .
RUN pip install -r ./requirements.txt

# Helm
RUN curl -sLO https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz && tar -xzf helm-${HELM_VERSION}-linux-amd64.tar.gz && mv linux-amd64/helm /usr/local/bin/helm && chmod +x /usr/local/bin/helm && rm -rf helm-${HELM_VERSION}-linux-amd64.tar.gz linux-amd64

ENV HELM_PATH_CACHE /var/cache
ENV HELM_CONFIG_HOME /tmp/helm/config
ENV HELM_CACHE_HOME /tmp/helm/cache

RUN mkdir -p /bin /rendered
WORKDIR "/source"
COPY helm2yaml.py k8envsubst.py /bin/

ENTRYPOINT ["/bin/helm2yaml.py"]

# Default is read KRM function 'ResourceList' from stdin
# https://github.com/kubernetes-sigs/kustomize/blob/master/cmd/config/docs/api-conventions/functions-spec.md
CMD ["--output", "stdout", "krm", "-f", "-"]
