## Kubernetes application deployment utilities

This tool reads [Helmsman](https://github.com/Praqma/helmsman) and
[FluxCD](https://fluxcd.io/) Kubernetes applications specs and allows for
running Helm2/Helm3 them to deploy applications to Kubernetes or, alterntively,
to render the resulting application YAML. The latter allows for keeping an audit
trail on the actual YAMl deployed to Kubernetes.
