FROM python:3.7.4-slim-stretch

ARG HELM2_VERSION="v2.16.1"
ENV HELM2_VERSION=$HELM2_VERSION
ARG HELM3_VERSION="v3.0.0"
ENV HELM3_VERSION=$HELM3_VERSION

RUN apt-get -y update && apt-get install -y curl && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ADD requirements.txt .
RUN pip install -r ./requirements.txt

# Helm 2
RUN curl -sLO https://get.helm.sh/helm-${HELM2_VERSION}-linux-amd64.tar.gz && tar -xzf helm-${HELM2_VERSION}-linux-amd64.tar.gz && mv linux-amd64/helm /usr/local/bin/helm2 && chmod +x /usr/local/bin/helm2 && rm -rf helm-${HELM2_VERSION}-linux-amd64.tar.gz linux-amd64

# Helm 3
RUN curl -sLO https://get.helm.sh/helm-${HELM3_VERSION}-linux-amd64.tar.gz && tar -xzf helm-${HELM3_VERSION}-linux-amd64.tar.gz && mv linux-amd64/helm /usr/local/bin/helm && chmod +x /usr/local/bin/helm && rm -rf helm-${HELM3_VERSION}-linux-amd64.tar.gz linux-amd64

RUN mkdir -p /bin /rendered
WORKDIR "/src"
COPY helm2yaml.py k8envsubst.py /bin/

ENTRYPOINT ["/bin/helm2yaml.py"]
CMD ["--help"]
