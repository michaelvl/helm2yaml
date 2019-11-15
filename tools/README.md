```shell
$ terraform.sh version
```

```shell
$ kubectl.sh version
```

```shell
$ helm.sh version
$ helm.sh repo list
```

```shell
$ sonobuoy.sh run -m quick
$ sonobuoy.sh run -m certified-conformance
$ sonobuoy.sh status
$ sonobuoy.sh logs -f
$ results=$(tools/sonobuoy.sh retrieve | sed 's/\r//')
$ sonobuoy.sh results $results
$ sonobuoy.sh delete --all
```