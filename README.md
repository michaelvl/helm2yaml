## Kubernetes application deployment utilities

This tool reads [Helmsman](https://github.com/Praqma/helmsman) and
[FluxCD](https://fluxcd.io/) Kubernetes applications specs and allows for
running Helm2 or Helm3 to to deploy applications to Kubernetes or, alternatively,
to render the resulting application YAML. The latter allows for keeping an audit
trail on the actual YAML deployed to Kubernetes.

The following Helmsman command:

```
helmsman --apply -f my-app.yaml
```

can be replaced by:

```
helm-up.py --apply helmsman --apply -f my-app.yaml
```

The tool helm-up is deliberately made Helmsman compatible, i.e. deployment
scripts could have the helmsman binary specified through an environment
variable as follows:

```
HELMSMAN=helmsman
$HELMSMAN --apply -f my-app.yaml
```

Replacing helmsman can then be done by changing the `HELMSMAN` env variable with:

```
HELMSMAN='helm-up.py --apply helmsman'
```

### GitOps

While using Helm to deploy applications directly onto a Kubernetes cluster is
very common it is also a cloud-native anti-pattern IMHO. Using Helm this way
means that Helm on-the-fly renders the final YAML which are deployed to the
cluster and this YAML is not retained in any other places than in the cluster.

For exactly the same reasons as why we build containers, the resulting YAMl
should be retained as an artifact such that we both have an audit trail for what
was actually deployed and such that we can be sure we can re-deploy the
application without having to re-run Helm to re-render the YAML.

With the helm-up tool, the final YAML can be retained by using the `--render-to`
argument as follows:

```
helm-up.py --render-to final-app.yaml helmsman -f helmsman-app-spec.yaml
kubectl apply -f final-app.yaml
```

Similarly wuth Flux application specs:

```
helm-up.py --render-to final-app.yaml fluxcd -f fluxcd-app-spec.yaml
kubectl apply -f final-app.yaml
```

and here `final-app.yaml` could be retained for the audit trail.  If the final
YAML is retained in e.g. git, the `kubectl apply` command could be replaced by
deployment on Kubernetes with Flux in a non-Helm mode, i.e. GitOps with an audit
trail.

A GitOps pipeline example is shown below:

![GitOps pipelines](doc/gitops.png)

### YAML Audit

Before the final YAML is deployed to a Kubernetes cluster, it can be validated
using e.g. [kubeaudit](https://github.com/Shopify/kubeaudit). E.g.

```
# First render the final YAML based on a Helmsman application spec
./helm-up.py --apply --render-to prometheus-final.yaml -b ~/bin/helm3 helmsman -f examples/prometheus.yaml
# Then run kubeaudit to validate the YAML
kubeaudit nonroot -v ERROR -f prometheus-final.yaml
```

This will produce errors like the following:

```
ERRO[0000] RunAsNonRoot is not set in ContainerSecurityContext, which results in root user being allowed!
```

which can be used to fail the GitOps pipeline for the application deployment.

### Using Helm3

Using `--apply` with helm-up (not to be confused with the second `--apply` shown
above after the `helmsman` sub-command, which is only there to be drop-in
compatible with Helmsman) will run helm to apply the application spec to a
Kubernetes cluster. To use an alternative Helm command, e.g. helm3, one could
specify the Helm command as follows:

```
helm-up.py --apply -b ~/bin/helm3 helmsman -f my-app.yaml
```

### Notes

`helm template` ignores namespace, i.e. the namespace is not included in the rendered YAML.

Helm2 does not accept repository on the `template` action, i.e. it is generally
recommended to use helm3.
