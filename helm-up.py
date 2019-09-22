#!/usr/bin/env python3

import sys, os
import string
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
        apps = yaml.load(fs)
        repos = apps.get('helmRepos', dict())
        if 'apps' in apps:
            for app_name in apps['apps'].keys():
                app = apps['apps'][app_name]
                logging.debug('App {}: {}'.format(app_name, app))
                chart_repo = app['chart'].split('/')[0]
                if chart_repo not in repos:
                    raise ParseError("Repo '{}' not found".format(chart_repo))
                repo = repos[chart_repo]
                new_app = {'rel_name':  app_name,
                           'namespace': app['namespace'],
                           'repo':      repo,
                           'chart':     app['chart'].split('/')[1],
                           'version':   app['version'],
                           'dirname':   dirname
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
                   #'repo':      repo,
                   #'chart':     app['chart'].split('/')[1],
                   #'version':   app['version'],
        }
        chart_keys = ['repository', 'name',  'version']
        new_keys =   ['repository', 'chart', 'version']
        if set(chart_keys).issubset(chart.keys()):
            for ck,ckn in zip(chart_keys, new_keys):
                new_app[ckn] = chart[ck]
        new_app['set'] = spec.get('values', dict())
        specs.append(new_app)
    return specs

def run_helm(specs, args):
    helm_bin = args.helm_bin
    tmpdir = tempfile.mkdtemp()
    logging.debug("Using temp dir: '{}'".format(tmpdir))
    for app in specs:
        # Render-to overrides apply
        if args.render_to:
            cmd = '{} template --namespace {} --repo {} {} {}'.format(helm_bin, app['namespace'], app['repo'], app['rel_name'], app['chart'])
        elif args.apply:
            cmd = '{} upgrade --install --namespace {} --repo {} {} {}'.format(helm_bin, app['namespace'], app['repo'], app['rel_name'], app['chart'])
        for k,v in app['set'].items():
            if type(v) is str:
                cmd += ' --set {}={}'.format(k,string.Template(v).substitute(os.environ))
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
        logging.debug('Helm command: {}'.format(cmd))
        out = subprocess.check_output(cmd, shell=True)
        # Render-to overrides apply
        if args.render_to:
            with fopener(args.render_to) as fh:
                print(out.decode('UTF-8','ignore'), file=fh)
        elif args.apply:
            for ln in out.split(b'\n'):
                logging.info(str(ln))

def do_helmsman(args):
    logging.debug('Helmsman spec files: {}'.format(args.helmsman))
    for fn in args.helmsman:
        specs = parse_helmsman(fn)
        logging.debug('Parsed Helmsman spec: {}'.format(pprint.pformat(specs)))
        if args.apply or args.render_to:
            run_helm(specs, args)

def do_flux(args):
    logging.debug('Flux spec files: {}'.format(args.flux))
    for fn in args.flux:
        specs = parse_flux(fn)
        logging.debug('Parsed Flux spec: {}'.format(pprint.pformat(specs)))
        if args.apply or args.render_to:
            run_helm(specs, args)


def main():
    parser = argparse.ArgumentParser(description='Helm Update Frontend')
    parser.add_argument('-l', dest='log_level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the log level')
    parser.add_argument('--render-to', default=None)
    parser.add_argument('-b', dest='helm_bin', default='helm')
    parser.add_argument('--apply', default=False, action='store_true')

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

    return args.func(args)

if __name__ == "__main__":
   sys.exit(main())
