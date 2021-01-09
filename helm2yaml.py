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
                    logging.info('Skiping disabled deployment {}'.format(app_name))
                    continue
                new_app['set'] = app.get('set', dict())
                new_app['valuesfiles'] = app.get('valuesFiles', [])
                specs.append(new_app)
    return specs

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

def yaml2dict(app):
    res_out = []
    for res in app.split('\n---\n'):
        res = string.Template(res).safe_substitute(os.environ)
        res = yaml.load(res, Loader=yaml.FullLoader)
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
        cmd = '{} fetch --destination {} --repo {} --version {} {}'.format(args.helm_bin, chartdir, app['repository'], app['version'], app['chart'])
        logging.debug('Helm command: {}'.format(cmd))
        out = subprocess.check_output(cmd, shell=True)
        logging.debug(out)

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

def resource_sort(res, args):
    '''Sort resource list by resource name, but without changing overall resource kind sorting'''
    if args.no_sort:
        return res
    out = []
    tmp = []
    last_kind = None
    for r in res:
        kind = r['kind']
        if last_kind and kind != last_kind:
            out += sorted(tmp, key=lambda r: r['metadata']['name'])
            tmp = []
        tmp.append(r)
        last_kind = kind
    out += sorted(tmp, key=lambda r: r['metadata']['name'])
    return out

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
    tmpdir = tempfile.mkdtemp()
    out = subprocess.check_output('mkdir -p {}'.format(tmpdir), shell=True)
    logging.debug("Run helm: Using tmp dir: '{}'".format(tmpdir))

    if args.local_chart_path:
        chartdir = args.local_chart_path
    else:
        chartdir = tempfile.mkdtemp()+'/charts'
    logging.debug("Run helm: Using chart dir: '{}'".format(tmpdir))

    apps = []
    for app in specs:
        helm_fetch_chart(app, args, chartdir, tmpdir)
        cmd = '{} template --include-crds {} --namespace {}'.format(args.helm_bin, app['rel_name'], app['namespace'])
        if args.kube_version:
            cmd += ' --kube-version {}'.format(args.kube_version)
        for apiver in args.api_versions:
            cmd += ' --api-versions {}'.format(apiver)
        for k,v in app['set'].items():
            if type(v) is str:
                cmd += " --set {}='{}'".format(k,string.Template(v).safe_substitute(os.environ))
            else:
                cmd += ' --set {}={}'.format(k,v)
        for vf in app['valuesfiles']:
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

        res = resource_sort(res, args)
        res_ns = resource_sort(res_ns, args)
        secrets = resource_sort(secrets, args)
        secrets_ns = resource_sort(secrets_ns, args)
        resource_list('Render-ready resources without explicit namespace', res)
        resource_list('Render-ready resources with explicit namespace', res_ns)
        resource_list('Render-ready secrets without explicit namespace', secrets)
        resource_list('Render-ready secrets with explicit namespace', secrets_ns)

        if not args.list_images:
            fnames = [render_to, render_w_ns_to, render_secrets_to, render_secrets_w_ns_to]
            sources = [res, res_ns, secrets, secrets_ns]
            for fname, src in zip(fnames, sources):
                if fname and len(src)>0:
                    with fopener(fname) as fh:
                        for r in src:
                            print(yaml.dump(r), file=fh)
                            print('---', file=fh)
            if render_namespace_to:
                with fopener(render_namespace_to) as fh:
                    print(get_namespace_resource(args, app), file=fh)
    return apps

def do_helmsman(args):
    logging.debug('Helmsman spec files: {}'.format(args.helmsman))
    for fn in args.helmsman:
        specs = parse_helmsman(fn)
        logging.debug('Parsed Helmsman spec: {}'.format(pprint.pformat(specs)))
        return run_helm(specs, args)

def do_flux(args):
    logging.debug('Flux spec files: {}'.format(args.flux))
    for fn in args.flux:
        specs = parse_flux(fn)
        logging.debug('Parsed Flux spec: {}'.format(pprint.pformat(specs)))
        return run_helm(specs, args)


def main():
    parser = argparse.ArgumentParser(description='Helm Update Frontend')
    parser.add_argument('-l', dest='log_level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the log level')

    parser.add_argument('--render-path', default='rendered')
    parser.add_argument('--add-namespace-to-path', default=False, action='store_true',
                        help='Add destination namespace to rendered files')
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

    subparsers = parser.add_subparsers()
    parser_helmsman = subparsers.add_parser('helmsman')
    parser_helmsman.set_defaults(func=do_helmsman)
    parser_fluxcd = subparsers.add_parser('fluxcd')
    parser_fluxcd.set_defaults(func=do_flux)
    
    parser_helmsman.add_argument('-f', dest='helmsman', action='append', default=[])
    parser_helmsman.add_argument('--apply', default=False, dest='helmsman_apply', action='store_true', help='Dummy, for compatibility with Helmsman')
    parser_helmsman.add_argument('--no-banner', action='store_true', help='Dummy, for compatibility with Helmsman')
    parser_helmsman.add_argument('--keep-untracked-releases', action='store_true', help='Dummy, for compatibility with Helmsman')

    parser_fluxcd.add_argument('-f', dest='flux', action='append', default=[])

    args = parser.parse_args()
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
