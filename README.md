## Kubernetes application deployment utilities

This repository contain tools for implementatin GitOps with Helm.

With `helm install` the Kubernetes resource YAML is not retained outside of
Kubernetes. This is an anti-pattern in CI/CD, where we strive to separate the
application building, packaging and running stages.  With Helm-based GitOps we
should consider the Helm-to-YAML process as a separate process from the actual
deployment. The YAML resulting from running `helm install` is the result of the
helm chart version, the Kubernetes API capabilities, whether the chart was
installed already and the values we specify for the configuration. With all
these moving parts, the resulting YAML should be retained similarly to how we
retain the binary artifact from source-code compilation.

The `helm2yaml` tool reads [Helmsman](https://github.com/Praqma/helmsman) and
[FluxCD](https://fluxcd.io/) Kubernetes applications specs and allows for
running Helm2 or Helm3 to render the resulting application Kubernetes resource
YAMLs. This allows for keeping an audit trail on the actual YAML deployed
to Kubernetes.

The following Helmsman command:

```
helmsman --apply -f my-app.yaml
```

can be replaced by:

```
helm2yaml.py --apply helmsman --apply -f my-app.yaml
```

The tool helm2yaml is deliberately made Helmsman compatible, i.e. deployment
scripts could have the helmsman binary specified through an environment
variable as follows:

```
HELMSMAN=helmsman
$HELMSMAN --apply -f my-app.yaml
```

Replacing helmsman can then be done by changing the `HELMSMAN` env variable with:

```
HELMSMAN='helm2yaml.py --apply helmsman'
```

### GitOps

While using Helm to deploy applications directly onto a Kubernetes cluster is
very common it is also a cloud-native anti-pattern IMHO. Using Helm this way
means that Helm on-the-fly renders the final YAML which are deployed to the
cluster and this YAML is not retained in any other places than in the cluster.

For exactly the same reasons as why we build containers, the resulting YAML
should be retained as an artifact such that we both have an audit trail for what
was actually deployed and such that we can be sure we can re-deploy the
application without having to re-run Helm to re-render the YAML.

With the helm2yaml tool, the final YAML can be retained by using the `--render-to`
argument as follows:

```
helm2yaml.py --render-to final-app.yaml helmsman -f helmsman-app-spec.yaml
kubectl apply -f final-app.yaml
```

Similarly wuth FluxCD application specs:

```
helm2yaml.py --render-to final-app.yaml fluxcd -f fluxcd-app-spec.yaml
kubectl apply -f final-app.yaml
```

and here `final-app.yaml` could be retained for the audit trail.  If the final
YAML is retained in e.g. git, the `kubectl apply` command could be replaced by
deployment on Kubernetes with Flux in a non-Helm mode, i.e. GitOps with an audit
trail.

#### Handling Secrets

If the application deployment contains secrets which should not be included in
the rendered YAML, these secrets could be injected at the YAML deployment stage
using e.g. `envsubst`. Note however, that `envsubst` replace all environment
variable occurences and e.g. shell scripts being passed into configmaps could
have environment variables wrongly replaced (potentially with empty
strings). The Grafana test that is part of the Grafana Helm chart is an example
of such a situation. If `envsubst` us used, the specific variables that should
be replaced should be specified as part of the `envsubst` invocation.

**Beware, that secrets have values base64 encoded, i.e. substituting environment
  variables in Kubernetes secrets is not readily possible with `envsubst`.**
  
To work-around this, use the `k8envsubst.py` utility - see the `helmsman.sh`
Helmsman-replacement script for how to do this. The `k8envsubst.py` utility also
replaces only defined environment variables, i.e. it does not break shell
scripts in configmaps.

#### GitOps Application Deployment Pipeline

A GitOps pipeline example is shown below:

![GitOps pipelines](doc/gitops.png)

### YAML Audit

Before the final YAML is deployed to a Kubernetes cluster, it can be validated
using e.g. [kubeaudit](https://github.com/Shopify/kubeaudit). E.g.

```
# First render the final YAML based on a Helmsman application spec
./helm2yaml.py --apply --render-to prometheus-final.yaml -b ~/bin/helm3 helmsman -f examples/prometheus.yaml
# Then run kubeaudit to validate the YAML
kubeaudit nonroot -v ERROR -f prometheus-final.yaml
```

This will produce errors like the following:

```
ERRO[0000] RunAsNonRoot is not set in ContainerSecurityContext, which results in root user being allowed!
```

which can be used to fail the GitOps pipeline for the application deployment.

### Using Helm3

Using `--apply` with helm2yaml (not to be confused with the second `--apply` shown
above after the `helmsman` sub-command, which is only there to be drop-in
compatible with Helmsman) will run helm to apply the application spec to a
Kubernetes cluster. To use an alternative Helm command, e.g. helm3, one could
specify the Helm command as follows:

```
helm2yaml.py --apply -b ~/bin/helm3 helmsman -f my-app.yaml
```

### Running from a Container

The helm2yaml tool is available as a container, e.g. see the `helmsman.sh`
Helmsman-replacement script.

### Notes

`helm template` ignores namespace, i.e. the namespace is not included in the
rendered YAML. To include a namespace resource, use the `--render-namespace-to`
argument.  Applying rendered YAML with `kubectl` should use an explicit
namespace argument - see the `helmsman.sh` Helmsman-replacement script for an
example. Charts that create resources in multiple namespaces may be problematic
- see e.g. [Helm issue
1744](https://github.com/jetstack/cert-manager/issues/1744). Luckily such charts
are rare - known examples are `cert-manager` and `metrics-server`.

Using `helm template` validates the YAML according to the default set of API
versions. This might not suffice for some charts and thus additional APIs could
be enabled with the `--api-versions` argument - see the `helmsman.sh`
Helmsman-replacement script for examples.

Helm2 does not accept repository on the `template` action, i.e. it is generally
recommended to use helm3.

With Helm applying resources to Kubernetes, a full diff will be applied
according to the deployed chart, i.e. if subsequent versions of a chart remove
resources, these will be deleted from Kubernetes. A render-and-run-kubectl
approach will thus not delete resources removed between different chart
versions. Allowing Helm to delete resources is probably also not a good idea in
production environments!

Dependencies (requirements.yaml in a chart) are handled properly.

Helm use [hooks](https://github.com/helm/helm/blob/master/docs/charts_hooks.md)
to deploy groups of resources at different points in the deployment lifecycle,
e.g. a resource with an `helm.sh/hook` annotation containing `post-install`
means that this resource should be deployed after the main resources. With `helm
template` the hook statemachine is not available and resources that normally
would not be deployed might be deployed (e.g. test resources).