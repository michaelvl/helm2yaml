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
                chart_repo = app['chart'].split('/')[0]
                if chart_repo not in repos:
                    raise ParseError("Repo '{}' not found".format(chart_repo))
                if not app['enabled']:
                    logging.info('Skiping disabled deployment {}'.format(app_name))
                    continue
                repo = repos[chart_repo]
                new_app = {'rel_name':   app_name,
                           'namespace':  app['namespace'],
                           'repository': repo,
                           'chart':      app['chart'].split('/')[1],
                           'version':    app['version'],
                           'dirname':    dirname
                }
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
    for res in app.split('---\n'):
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
def helm_fetch_chart(app, args, tmpdir):
    logging.debug("Using temp dir: '{}'".format(tmpdir))
    cmd = '{} fetch --untar --untardir {}/charts --repo {} --version {} {}'.format(args.helm_bin, tmpdir, app['repository'], app['version'], app['chart'])
    logging.debug('Helm command: {}'.format(cmd))
    out = subprocess.check_output(cmd, shell=True)

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
            match = False
            if 'metadata' in r and 'annotations' in r['metadata']:
                anno = r['metadata']['annotations']
                logging.debug('Resource {}/{} annotations: {}'.format(r['kind'], r['metadata']['name'], anno))
                if helm_hook_anno in anno:
                    if anno[helm_hook_anno] in args.hook_filter:
                        logging.debug('Resource {}/{} annotation value {} matched'.format(r['kind'], r['metadata']['name'], anno[helm_hook_anno]))
                        match = True
                else: # No hook annotation
                    if len(args.hook_filter)==1 and args.hook_filter[0]=='':
                        match = True
            else: # No annotation
                if len(args.hook_filter)==1 and args.hook_filter[0]=='':
                    match = True
            if match:
                logging.debug('Resource {}/{} matched'.format(r['kind'], r['metadata']['name']))
                out.append(r)
            else:
                logging.info('Filtering resource {}/{}'.format(r['kind'], r['metadata']['name']))
    return res

def run_helm(specs, args):
    subprocess.check_output('helm init {}'.format(args.helm_init_args), shell=True)

    tmpdir = tempfile.mkdtemp()
    logging.debug("Using temp dir: '{}'".format(tmpdir))
    apps = []
    for app in specs:
        helm_fetch_chart(app, args, tmpdir)
        cmd = '{} template {} --namespace {}'.format(args.helm_bin, app['rel_name'], app['namespace'])
        if args.kube_version:
            cmd += ' --kube-version {} {}/charts/{}'.format(args.kube_version)
        for apiver in args.api_versions:
            cmd += ' --api-versions {}'.format(apiver)
        for k,v in app['set'].items():
            if type(v) is str:
                cmd += ' --set {}={}'.format(k,string.Template(v).safe_substitute(os.environ))
            else:
                cmd += ' --set {}={}'.format(k,v)
        for vf in app['valuesfiles']:
            with open('{}/{}'.format(tmpdir, vf), 'w') as vfn_dst:
                with open('{}/{}'.format(app['dirname'], vf), 'r') as vfn_src:
                    src = vfn_src.read()
                    dst = string.Template(src).safe_substitute(os.environ)
                    logging.debug('Env expanded values: {}'.format(dst))
                    vfn_dst.write(dst)
            cmd += ' --values {}/{}'.format(tmpdir, vf)
        cmd += ' {}/charts/{}'.format(tmpdir, app['chart'])
        logging.debug('Helm command: {}'.format(cmd))
        out = subprocess.check_output(cmd, shell=True)
        out = out.decode('UTF-8','ignore')
        res = yaml2dict(out)
        res = resource_filter(res, args)
        apps.append(res)
        if args.render_to:
            with fopener(args.render_to) as fh:
                print(out, file=fh)
        if args.render_namespace_to:
            with fopener(args.render_namespace_to) as fh:
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
    parser.add_argument('--render-to', default=None)
    parser.add_argument('-b', dest='helm_bin', default='helm')
    parser.add_argument('--helm-init-args', default='')
    parser.add_argument('--kube-version', default=None)
    parser.add_argument('--api-versions', default=[], action='append')
    parser.add_argument('--render-namespace-to', default=None,
                        help='Render Namespace resource (implicitly in Helm)')
    parser.add_argument('--list-images', action='store_true')
    parser.add_argument('--hook-filter', default=[], action='append',
                        help='Resource hook filter. Annotation values matching are removed from rendered output')

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
