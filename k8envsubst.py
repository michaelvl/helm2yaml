#!/usr/bin/env python3

import sys, os
import string
import yaml
import logging
import base64

def main():
    inp = open(0).read()
    resources = inp.split('---\n')
    logging.debug('Found {} resource elements'.format(len(resources)))
    patched_resources = []
    for res in resources:
        res = string.Template(res).safe_substitute(os.environ)
        res = yaml.load(res, Loader=yaml.FullLoader)
        if res:
            if 'kind' in res and 'data' in res and res['kind']=='Secret':
                for k,v64 in res['data'].items():
                    v = base64.b64decode(v64)
                    vrep = string.Template(v.decode('UTF-8','ignore')).safe_substitute(os.environ).encode('UTF-8')
                    res['data'][k] = base64.b64encode(vrep).decode('UTF-8','ignore')
            patched_resources.append(yaml.dump(res, default_flow_style=False)) # FIXME, Use Kubernetes natural sort order
    print('---\n'.join(patched_resources))

if __name__ == "__main__":
   sys.exit(main())
