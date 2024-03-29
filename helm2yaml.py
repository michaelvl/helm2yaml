#!/usr/bin/env python3

import sys, os
import string, io
import argparse
import subprocess
import yaml
import logging
import pprint
import tempfile
import contextlib

class ParseError(Exception):
    pass

@contextlib.contextmanager
def fopener(filename=None):
    if filename and filename != '-':
        fh = open(filename, 'w')
    else:
        fh = sys.stdout

    try:
        yield fh
    finally:
        if fh is not sys.stdout:
            fh.close()

@contextlib.contextmanager
def fopener_read(filename=None):
    if filename and filename != '-':
        fh = open(filename, 'r')
    else:
        fh = sys.stdin

    try:
        yield fh
    finally:
        if fh is not sys.stdin:
            fh.close()

def parse_helmsman(fname):
    specs = []
    repo = {}
    dirname = os.path.dirname(fname)
    if dirname == '':
        dirname = '.'
    logging.debug("Loading Helmsman spec '{}'. Dirname '{}'".format(fname, dirname))
    with open(fname, 'r') as fs:
        apps = yaml.load(fs, Loader=yaml.FullLoader)
        repos = apps.get('helmRepos', dict())
        if 'apps' in apps:
            for app_name in apps['apps'].keys():
                app = apps['apps'][app_name]
                logging.debug('App {}: {}'.format(app_name, app))
                if '/' in app['chart']:
                    chart_repo, chart = app['chart'].split('/')
                else:
                    chart_repo = None
                    chart = app['chart']
                new_app = {'rel_name':   app_name,
                           'namespace':  app['namespace'],
                           'chart':      chart,
                           'version':    app['version'],
                           'dirname':    dirname
                }
                if chart_repo:
                    if chart_repo not in repos:
                        logging.warning("Repo '{}' not found in spec file".format(chart_repo))
                    else:
                        repo = repos[chart_repo]
                        new_app['repository'] = repo

                if not app['enabled']:
                    logging.info('Skipping disabled deployment {}'.format(app_name))
                    continue
                new_app['set'] = app.get('set', dict())
                new_app['valuesfiles'] = app.get('valuesFiles', [])
                specs.append(new_app)
    return specs

# Export chart spec as KRM format
# See
#  - https://catalog.kpt.dev/render-helm-chart/v0.1/?id=render-helm-chart
#  - https://catalog.kpt.dev/render-helm-chart/v0.2/
#  - https://github.com/GoogleContainerTools/kpt-functions-catalog/tree/master/functions/go/render-helm-chart
def export_krmfmt(specs, outfname):
    logging.debug('Parsed chart spec: {}'.format(pprint.pformat(specs)))
    #return export_krmfmt_0_1_0(specs, outfname)
    return export_krmfmt_0_2_0(specs, outfname)

def export_krmfmt_0_2_0(specs, outfname):
    with fopener(outfname) as fh:
        print('apiVersion: fn.kpt.dev/v1alpha1', file=fh)
        print('kind: RenderHelmChart', file=fh)
        print('metadata:', file=fh)
        print('  name: render-chart', file=fh)
        print('  annotations:', file=fh)
        print('    config.kubernetes.io/local-config: "true"', file=fh)
        print('helmCharts:', file=fh)
        print('- chartArgs:', file=fh)
        for ka,kb in [('name', 'chart'), ('version', 'version'), ('repo', 'repository')]:
            print('    {}: {}'.format(ka, specs[0][kb]), file=fh)
        print('  templateOptions:', file=fh)
        for ka,kb in [('releaseName','rel_name'), ('namespace','namespace')]:
            print('    {}: {}'.format(ka, specs[0][kb]), file=fh)
        if len(specs[0]['valuesfiles'])>0 or specs[0]['set']:
            print('    values:', file=fh)
        if len(specs[0]['valuesfiles'])==1:
            print('      valuesFile: {}'.format(specs[0]['valuesfiles'][0]), file=fh)
        elif len(specs[0]['valuesfiles'])>1:
            print('      valuesFiles:', file=fh)
            for fn in specs[0]['valuesfiles']:
                print('      - {}'.format(fn), file=fh)
        if specs[0]['set']:
            print('      valuesInline:', file=fh)
            y = yaml.dump(specs[0]['set'], default_flow_style=False)
            for ln in str(y).split('\n'):
                print('        '+ln, file=fh)

def export_krmfmt_0_1_0(specs, outfname):
    with fopener(outfname) as fh:
        print('helmCharts:', file=fh)
        prefix = '- '
        for ka,kb in [('name', 'chart'), ('version', 'version'), ('repo', 'repository'),
                                          ('releaseName','rel_name'), ('namespace','namespace')]:
            print('{}{}: {}'.format(prefix, ka, specs[0][kb]), file=fh)
            prefix = '  '
        if len(specs[0]['valuesfiles'])==1:
            print('  valuesFile: {}'.format(specs[0]['valuesfiles'][0]), file=fh)
        elif len(specs[0]['valuesfiles'])>1:
            print('  valuesFiles:', file=fh) # This is an extension - format does not support lists
            for fn in specs[0]['valuesfiles']:
                print('  - {}'.format(fn), file=fh)
        if specs[0]['set']:
            print('  valuesInline:', file=fh)
            y = yaml.dump(specs[0]['set'], default_flow_style=False)
            for ln in str(y).split('\n'):
                print('    '+ln, file=fh)

# https://github.com/GoogleContainerTools/kpt-functions-catalog/tree/master/functions/go/render-helm-chart
# https://catalog.kpt.dev/render-helm-chart/v0.1/
def parse_krm(fname):
    specs = []
    repo = {}
    dirname = os.path.dirname(fname)
    if dirname == '':
        dirname = '.'
    logging.debug("Loading KRM spec '{}'. Dirname '{}'".format(fname, dirname))
    with fopener_read(fname) as fs:
        apps = yaml.load(fs, Loader=yaml.FullLoader)
        if 'kind' in apps and apps['kind'] == 'ResourceList':
            # For KRM functions, the Helm chart spec is embedded in 'functionConfig'
            apps = apps['functionConfig']
        for app in apps.get('helmCharts', []):
            if 'templateOptions' in app and 'chartArgs' in app:   # v0.2.0 format
                version = '0.2.0'
                templateOptions = app['templateOptions']
                chartArgs = app['chartArgs']
                new_app = {'rel_name':   templateOptions['releaseName'],
                           'namespace':  templateOptions['namespace'],
                           'chart':      chartArgs['name'],
                           'repository': chartArgs['repo'],
                           'version':    chartArgs['version'],
                           'dirname':    dirname,
                           'valuesfiles': [],
                           'set':        {}
                }
                if 'apiVersions' in templateOptions:
                    new_app['apiVersions'] = templateOptions['apiVersions']
                if 'values' in templateOptions:
                    values = templateOptions['values']
                    new_app['set'] = values.get('valuesInline', dict())
                    if 'valuesFile' in values:
                        new_app['valuesfiles'] += [values.get('valuesFile')]
                    new_app['valuesfiles'] += values.get('valuesFiles', [])
                specs.append(new_app)
            else:  # assume v0.1.0 format
                version = '0.1.0'
                new_app = {'rel_name':   app['releaseName'],
                           'namespace':  app['namespace'],
                           'chart':      app['name'],
                           'repository': app['repo'],
                           'version':    app['version'],
                           'dirname':    dirname,
                           'valuesfiles': []
                }
                new_app['set'] = app.get('valuesInline', dict())
                if 'valuesFile' in app:
                    new_app['valuesfiles'] += [app.get('valuesFile')]
                new_app['valuesfiles'] += app.get('valuesFiles', []) # Extension, v0.1.0 format does not support lists
                specs.append(new_app)
    return specs,version

def parse_flux(fname):
    specs = []
    repo = {}
    logging.debug("Loading Flux spec '{}'".format(fname))
    with open(fname, 'r') as fs:
        app = yaml.load(fs)
        meta = app['metadata']
        spec = app['spec']
        chart = spec['chart']
        new_app = {'rel_name':  spec['releaseName'],
                   'namespace': meta['namespace'],
                   'valuesfiles': []
        }
        chart_keys = ['repository', 'name',  'version']
        new_keys =   ['repository', 'chart', 'version']
        if set(chart_keys).issubset(chart.keys()):
            for ck,ckn in zip(chart_keys, new_keys):
                new_app[ckn] = chart[ck]
        new_app['set'] = spec.get('values', dict())
        specs.append(new_app)
    return specs

# Work-around for '=' as unquoted string
# https://github.com/yaml/pyyaml/issues/89
# https://github.com/prometheus-operator/prometheus-operator/pull/4897
class PatchedFullLoader(yaml.FullLoader):
    yaml_implicit_resolvers = yaml.FullLoader.yaml_implicit_resolvers.copy()
    yaml_implicit_resolvers.pop("=")

def yaml2dict(app):
    res_out = []
    for res in app.split('\n---\n'):
        res = string.Template(res).safe_substitute(os.environ)
        res = yaml.load(res, Loader=PatchedFullLoader)
        if res:
            res_out.append(res)
    return res_out

def list_images(app):
    img_list = []
    for res in app:
        spec = None
        if 'kind' in res and res['kind']=='Pod':
            spec = res['spec']
        if 'kind' in res and (res['kind']=='Deployment' or res['kind']=='StatefulSet' or res['kind']=='DaemonSet'):
            spec = res['spec']['template']['spec']
        containers = None
        if spec:
            containers = spec['containers']
            if 'initContainers' in spec:
                containers += spec['initContainers']
        if containers:
            logging.debug('Container list: {}'.format(containers))
            imgs = [c['image'] for c in containers]
            logging.debug('Images from {} {}: {}'.format(res['kind'], res['metadata']['name'], imgs))
            img_list += imgs

    img_list_set = set(img_list)
    img_out = (list(img_list_set))
    logging.debug('Images {}'.format(img_out))
    return img_out

# Particularly needed for Helm2 which do not have a --repo argument on 'template'
def helm_fetch_chart(app, args, chartdir, tmpdir):
    logging.debug("Fetch : Using chart dir: '{}'".format(chartdir))
    chart = '{}/{}-{}.tgz'.format(chartdir, app['chart'], app['version'])
    if os.path.exists(chart):
        logging.info('Using local chart: {}'.format(chart))
    else:
        if app['repository'].startswith('oci://'):
            cmd = '{} pull {}/{} --destination {} --version {}'.format(args.helm_bin, app['repository'], app['chart'], chartdir, app['version'])
        else:
            cmd = '{} pull --repo {} {} --destination {} --version {}'.format(args.helm_bin, app['repository'], app['chart'], chartdir, app['version'])
        logging.debug('Helm command: {}'.format(cmd))
        out = subprocess.check_output(cmd, shell=True)
        logging.debug(out)

    # Rename if chart does not follow common format as encoded in 'chart'
    if not os.path.exists(chart):
        logging.debug("No file '{}' found after pull into {}".format(chart, chartdir))
        options = os.listdir(chartdir)
        logging.debug("Chart options: {}".format(options))
        if len(options) == 1:
            logging.info("Normalizing chart file from {} to {}".format(options[0], chart))
            os.rename(chartdir+"/"+options[0], chart)
        else:
            logging.info("Dont know which file to use to normalize chart name: {}".format(options))

    cmd = 'tar -xzf {} --directory {}'.format(chart, tmpdir)
    logging.debug('Tar command: {}'.format(cmd))
    out = subprocess.check_output(cmd, shell=True)
    logging.debug(out)

    cmd = 'ls -laR {}'.format(tmpdir)
    logging.debug('Post helm-fetch ls command: {}'.format(cmd))
    out = subprocess.check_output(cmd, shell=True)
    logging.debug(out)

def get_namespace_resource(args, app):
    return '''
apiVersion: v1
kind: Namespace
metadata:
  name: {name}
'''.format(name=app['namespace'])

def resource_filter(res, args):
    helm_hook_anno = 'helm.sh/hook'
    out = []
    if args.hook_filter:
        logging.debug("Hook filter using '{}'".format(args.hook_filter))
        for r in res:
            remove = False
            if 'metadata' in r and 'annotations' in r['metadata']:
                anno = r['metadata']['annotations']
                logging.debug('Resource {}/{} annotations: {}'.format(r['kind'], r['metadata']['name'], anno))
                if anno and helm_hook_anno in anno:
                    if anno[helm_hook_anno] in args.hook_filter:
                        logging.debug('Resource {}/{} annotation value {} matched filter, skipping'.format(r['kind'], r['metadata']['name'], anno[helm_hook_anno]))
                        remove = True
            if remove:
                logging.info('Filtering resource {}/{}'.format(r['kind'], r['metadata']['name']))
            else:
                logging.debug('Resource {}/{} matched'.format(r['kind'], r['metadata']['name']))
                out.append(r)
    else:
        return res
    return out

def resource_api_upgrade(res, args):
    upgrades = [
        {'kind': ['StatefulSet', 'DaemonSet', 'Deployment', 'ReplicaSet'], 'api': {'from': 'apps/v1beta1', 'to': 'apps/v1'}},
        {'kind': ['StatefulSet', 'DaemonSet', 'Deployment', 'ReplicaSet'], 'api': {'from': 'apps/v1beta2', 'to': 'apps/v1'}},
        {'kind': ['Deployment'], 'api': {'from': 'extensions/v1beta1', 'to': 'apps/v1'}},
        {'kind': ['PodSecurityPolicy'], 'api': {'from': 'extensions/v1beta1', 'to': 'policy/v1beta1'}},
        {'kind': ['NetworkPolicy'], 'api': {'from': 'extensions/v1beta1', 'to': 'networking.k8s.io/v1'}}
    ]
    if args.auto_api_upgrade:
        logging.debug('Doing auto API upgrade')
        for r in res:
            api = r['apiVersion']
            kind = r['kind']
            name = r['metadata']['name']
            logging.debug('Resource {}/{} api: {}'.format(kind, name, api))
            for upg in upgrades:
                if kind in upg['kind'] and api==upg['api']['from']:
                    logging.warning('Upgrade API of {}/{} from {} to {}'.format(kind, name, api, upg['api']['to']))
                    r['apiVersion'] = upg['api']['to']
    return res

def resource_split_ns_no_ns(res, args):
    '''Split resource into a list of those that have a specific namespace and those without namespace'''
    out = []
    out_ns = []
    for r in res:
        kind = r['kind']
        name = r['metadata']['name']
        logging.debug('Resource {}/{}'.format(kind, name))
        if 'namespace' in r['metadata']:
            out_ns.append(r)
        else:
            out.append(r)
    return out, out_ns

def resource_separate(res, kinds):
    '''Split out resource of specific kinds'''
    out = []
    out_sep = []
    for r in res:
        kind = r['kind']
        name = r['metadata']['name']
        logging.debug('Resource {}/{}'.format(kind, name))
        if kind in kinds:
            out_sep.append(r)
        else:
            out.append(r)
    return out, out_sep

def resource_list(header, res):
    logging.debug('{} ({} resources):'.format(header, len(res)))
    for r in res:
        if not set(['apiVersion', 'kind', 'metadata']).issubset(r.keys()):
            logging.error('Resource missing keys: {}'.format(r))
        api = r['apiVersion']
        kind = r['kind']
        name = r['metadata']['name']
        logging.debug('Resource {}/{}/{}'.format(api, kind, name))

def run_helm(specs, args):
    if args.skip_helm:
        return []

    tmpdir = tempfile.mkdtemp()
    out = subprocess.check_output('mkdir -p {}'.format(tmpdir), shell=True)
    logging.debug("Run helm: Using tmp dir: '{}'".format(tmpdir))

    if args.local_chart_path:
        chartdir = args.local_chart_path
    else:
        chartdir = tmpdir
    logging.debug("Run helm: Using chart dir: '{}'".format(tmpdir))

    apps = []
    for app in specs:
        helm_fetch_chart(app, args, chartdir, tmpdir)
        cmd = '{} template --include-crds {} --namespace {}'.format(args.helm_bin, app['rel_name'], app['namespace'])
        if args.kube_version:
            cmd += ' --kube-version {}'.format(args.kube_version)
        for apiver in args.api_versions:
            cmd += ' --api-versions {}'.format(apiver)
        for k,v in app.get('set', dict()).items():
            if type(v) is str:
                cmd += " --set {}='{}'".format(k,string.Template(v).safe_substitute(os.environ))
            else:
                cmd += ' --set {}={}'.format(k,v)
        for vf in app.get('valuesfiles', []):
            with open('{}/{}'.format(tmpdir, vf), 'w') as vfn_dst:
                with open('{}/{}'.format(app['dirname'], vf), 'r') as vfn_src:
                    src = vfn_src.read()
                    dst = string.Template(src).safe_substitute(os.environ)
                    logging.debug('Env expanded values in file {}:\n{}'.format(vf, dst))
                    vfn_dst.write(dst)
            cmd += ' --values {}/{}'.format(tmpdir, vf)
        cmd += ' {}/{}'.format(tmpdir, app['chart'])
        logging.debug('Helm command: {}'.format(cmd))
        out = subprocess.check_output(cmd, shell=True)
        out = out.decode('UTF-8','ignore')
        logging.debug('Output from Helm: {}'.format(out))
        res = yaml2dict(out)
        resource_list('Resources from Helm', res)
        res = resource_filter(res, args)
        res = resource_api_upgrade(res, args)
        resource_list('Upgraded resources', res)

        if args.add_namespace_to_path:
            base = args.render_path + '/' + app['namespace'] + '-' + app['rel_name']
            base_ns = args.render_path + '/' + args.namespace_filename_prefix + app['namespace'] + '-' + app['rel_name']
        else:
            base = args.render_path + '/' + app['rel_name']
            base_ns = args.render_path + '/' + args.namespace_filename_prefix + app['rel_name']
        render_to = base + '.yaml'
        render_namespace_to = base_ns + '-ns.yaml'
        render_w_ns_to = None
        render_secrets_to = None
        render_secrets_w_ns_to = None
        if args.separate_secrets:
            render_secrets_to = base + '-secrets.yaml'
        if args.separate_with_namespace:
            render_w_ns_to = base + '-w-ns.yaml'
            if args.separate_secrets:
                render_secrets_w_ns_to = base + '-secrets-w-ns.yaml'

        if render_w_ns_to:
            res, res_ns = resource_split_ns_no_ns(res, args)
        else:
            res_ns = []
        if render_secrets_to:
            res, secrets = resource_separate(res, ['Secret'])
        else:
            secrets = []
        if render_secrets_w_ns_to and render_w_ns_to:
            res_ns, secrets_ns = resource_separate(res_ns, ['Secret'])
        else:
            secrets_ns = []
        apps.append(res)
        apps.append(res_ns)
        apps.append(secrets)
        apps.append(secrets_ns)

        resource_list('Render-ready resources without explicit namespace', res)
        resource_list('Render-ready resources with explicit namespace', res_ns)
        resource_list('Render-ready secrets without explicit namespace', secrets)
        resource_list('Render-ready secrets with explicit namespace', secrets_ns)

        if not args.list_images:
            if args.output=='unwrap' or args.output=='file':
                fnames = [render_to, render_w_ns_to, render_secrets_to, render_secrets_w_ns_to]
                sources = [res, res_ns, secrets, secrets_ns]
                for fname, src in zip(fnames, sources):
                    if fname and len(src)>0:
                        if args.output=='unwrap':
                            fname = '-'
                        with fopener(fname) as fh:
                            for r in src:
                                print(yaml.dump(r), file=fh)
                                print('---', file=fh)
            if args.output=='stdout':
                fname = '-'
                with fopener(fname) as fh:
                    print('apiVersion: config.kubernetes.io/v1', file=fh)
                    print('kind: ResourceList', file=fh)
                    #print('items:', file=fh)
                    #  for r in src:
                    print(yaml.dump({'items': res + res_ns + secrets + secrets_ns}), file=fh)
            if args.add_namespace and render_namespace_to:
                with fopener(render_namespace_to) as fh:
                    print(get_namespace_resource(args, app), file=fh)
    return apps

def do_helmsman(args):
    logging.debug('Helmsman spec files: {}'.format(args.helmsman))
    for fn in args.helmsman:
        specs = parse_helmsman(fn)
        logging.debug('Parsed Helmsman spec: {}'.format(pprint.pformat(specs)))
        if args.export_krm:
            export_krmfmt(specs, args.export_krm)
        return run_helm(specs, args)

def do_flux(args):
    logging.debug('Flux spec files: {}'.format(args.flux))
    for fn in args.flux:
        specs = parse_flux(fn)
        logging.debug('Parsed Flux spec: {}'.format(pprint.pformat(specs)))
        return run_helm(specs, args)

def do_krm(args):
    logging.debug('KRM spec files: {}'.format(args.krm))
    for fn in args.krm:
        specs,krm_version = parse_krm(fn)
        logging.debug('Parsed KRM spec: {}'.format(pprint.pformat(specs)))
        if args.export_upgraded_krm:
            export_krmfmt(specs, args.export_upgraded_krm)
        return run_helm(specs, args)


def main():
    parser = argparse.ArgumentParser(description='Helm Update Frontend')
    parser.add_argument('-l', dest='log_level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the log level')

    parser.add_argument('--render-path', default='rendered')
    parser.add_argument('--add-namespace-to-path', default=False, action='store_true',
                        help='Add destination namespace to rendered files')
    parser.add_argument('--add-namespace', default=False, action='store_true', help='Add namespace resource')
    parser.add_argument('--namespace-filename-prefix', default='00-',
                        help='Prefix for namespace filename')
    parser.add_argument('--separate-with-namespace', default=False, action='store_true',
                        help='Separate out resources with explicit namespace spec')
    parser.add_argument('--separate-secrets', default=False, action='store_true',
                        help='Separate out secrets')
    parser.add_argument('-b', dest='helm_bin', default='helm')
    parser.add_argument('--helm-init-args', default='')
    parser.add_argument('--kube-version', default=None)
    parser.add_argument('--api-versions', default=[], action='append')
    parser.add_argument('--list-images', action='store_true')
    parser.add_argument('--hook-filter', default=[], action='append',
                        help='Resource hook filter. Annotation values matching are removed from rendered output')
    parser.add_argument('--auto-api-upgrade', default=False, action='store_true',
                        help='Automatically upgrade API changes, e.g. the 1.16.0 API deprecations')
    parser.add_argument('--no-sort', action='store_true', default=False,
                        help='Sort resources by name')
    parser.add_argument('--local-chart-path', default='')
    parser.add_argument('--skip-helm', default=False, action='store_true')
    parser.add_argument('-o', '--output', default='file', choices=['file', 'stdout', 'unwrap'])

    subparsers = parser.add_subparsers()
    parser_helmsman = subparsers.add_parser('helmsman')
    parser_helmsman.set_defaults(func=do_helmsman)
    parser_fluxcd = subparsers.add_parser('fluxcd')
    parser_fluxcd.set_defaults(func=do_flux)
    parser_krm = subparsers.add_parser('krm')
    parser_krm.set_defaults(func=do_krm)
    
    parser_helmsman.add_argument('-f', dest='helmsman', action='append', default=[])
    parser_helmsman.add_argument('--apply', default=False, dest='helmsman_apply', action='store_true', help='Dummy, for compatibility with Helmsman')
    parser_helmsman.add_argument('--no-banner', action='store_true', help='Dummy, for compatibility with Helmsman')
    parser_helmsman.add_argument('--keep-untracked-releases', action='store_true', help='Dummy, for compatibility with Helmsman')
    parser_helmsman.add_argument('--export-krm', help='Export KRM format spec filename')

    parser_fluxcd.add_argument('-f', dest='flux', action='append', default=[])

    parser_krm.add_argument('-f', dest='krm', action='append', default=[])
    parser_krm.add_argument('--export-upgraded-krm', help='Export upgraded KRM format spec filename')

    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr)
    logging.getLogger('').setLevel(getattr(logging, args.log_level))

    logging.debug('Env variables: {}'.format(pprint.pformat(os.environ)))

    if not hasattr(args, 'func'):
        parser.print_help()
        return -1
    apps = args.func(args)
    if args.list_images and apps:
        for app in apps:
            imgs = list_images(app)
            print("\n".join(imgs))

if __name__ == "__main__":
   sys.exit(main())
