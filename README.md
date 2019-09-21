## Kubernetes application deployment utilities

This tool reads [Helmsman](https://github.com/Praqma/helmsman) and
[FluxCD](https://fluxcd.io/) Kubernetes applications specs and allows for
running Helm2/Helm3 to to deploy applications to Kubernetes or, alternatively,
to render the resulting application YAML. The latter allows for keeping an audit
trail on the actual YAMl deployed to Kubernetes.

The following Helmsman command:

```
helmsman --apply -f my-app.yaml
```

can be replaced by:

```
helm-up.py --apply helmsman --apply -f my-app.yaml
```

The tool helm-up is deliberately made Helmsman compatible, i.e. deployment
scripts could have the helmsman program specified through an environment
variable as follows:

```
HELMSMAN=helmsman
$HELMSMAN --apply -f my-app.yaml
```

Replacing helmsman can then be done by changing the `HELMSMAN` env variable with:

```
HELMSMAN='helm-up.py --apply helmsman'
```

If one desires an audit trail for application deployment, the final YAML can be
retained by using the `--render-to` argument as follows:

```
helm-up.py --render-to final-app.yaml helmsman -f my-app.yaml
kubectl apply -f final-app.yaml
```

and here `final-app.yaml` could be retained for the audit trail.  If the final
YAML is retained in e.g. git, the `kubectl apply` command could be replaced by
deployment on Kubernetes with Flux in a non-Helm mode, i.e. GitOps with an audit
trail.

### Using Helm3

Using `--apply` with helm-up (not to be confused with the second `--apply` shown
above after the `helmsman` sub-command, which is only there to be drop-in
compatible with Helmsman) will run helm to apply the application spec to a
Kubernetes cluster. To use an alternative Helm command, e.g. helm3, one could
specify the Helm command as follows:

```
helm-up.py --apply -b ~/bin/helm3 helmsman -f my-app.yaml
```
