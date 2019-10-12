FROM python:3.7.4-slim-stretch

RUN apt-get -y update && apt-get install -y curl && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ADD requirements.txt .
RUN pip install -r ./requirements.txt

# Helm 2
RUN curl -sLO https://get.helm.sh/helm-v2.14.3-linux-amd64.tar.gz && tar -xzf helm-v2.14.3-linux-amd64.tar.gz && mv linux-amd64/helm /usr/local/bin && chmod +x /usr/local/bin/helm && rm -rf helm-v2.14.3-linux-amd64.tar.gz linux-amd64

# Helm 3
RUN curl -sLO https://get.helm.sh/helm-v3.0.0-beta.2-linux-amd64.tar.gz && tar -xzf helm-v3.0.0-beta.2-linux-amd64.tar.gz && mv linux-amd64/helm /usr/local/bin/helm3 && chmod +x /usr/local/bin/helm3 && rm -rf helm-v3.0.0-beta.2-linux-amd64.tar.gz linux-amd64

RUN mkdir -p /bin /rendered
WORKDIR "/src"
COPY helm2yaml.py /bin/

ENTRYPOINT ["/bin/helm2yaml.py"]
CMD ["--help"]
