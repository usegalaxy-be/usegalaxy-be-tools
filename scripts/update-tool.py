import yaml
import os
import glob
import copy
import argparse
import logging

from bioblend import toolshed

ts = toolshed.ToolShedInstance(url='https://toolshed.g2.bx.psu.edu')


def update_file(fn, owner=None, name=None, without=False):
    with open(fn + '.lock', 'r') as handle:
        locked = yaml.safe_load(handle)

    # Update any locked tools.
    for tool in locked['tools']:
        # If without, then if it is lacking, we should exec.
        logging.debug("Examining {owner}/{name}".format(**tool))

        if without:
            if 'revisions' in tool and not len(tool.get('revisions', [])) == 0:
                continue

        if not without and owner and tool['owner'] != owner:
            continue

        if not without and name and tool['name'] != name:
            continue

        logging.info("Fetching updates for {owner}/{name}".format(**tool))

        try:
            revs = ts.repositories.get_ordered_installable_revisions(tool['name'], tool['owner'])
        except Exception as e:
            print(e)
            continue

        logging.debug('TS revisions: %s' % ','.join(revs))

        # Add every installable revision we don't have yet, not just the latest.
        # Only looking at revs[-1] here meant any revision that was superseded
        # between two runs (e.g. two new revisions landing in the same week)
        # was silently never captured. TS doesn't support utf8 and we don't
        # want to either, hence str().
        missing = [str(r) for r in revs if str(r) not in tool.get('revisions', [])]
        if not missing:
            # Nothing new, don't rewrite the entry.
            continue

        logging.info("Found new revision(s) of {owner}/{name} ({revs})".format(revs=missing, **tool))

        if 'revisions' not in tool:
            tool['revisions'] = []
        tool['revisions'].extend(missing)

        tool['revisions'] = sorted(list(set( tool['revisions'] )))

    with open(fn + '.lock', 'w') as handle:
        yaml.dump(locked, handle, default_flow_style=False)



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('fn', type=argparse.FileType('r'), help="Tool.yaml file")
    parser.add_argument('--owner', help="Repository owner to filter on, anything matching this will be updated")
    parser.add_argument('--name', help="Repository name to filter on, anything matching this will be updated")
    parser.add_argument('--without', action='store_true', help="If supplied will ignore any owner/name and just automatically add the latest hash for anything lacking one.")
    parser.add_argument('--log', choices=('critical', 'error', 'warning', 'info', 'debug'), default='info')
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log.upper()))
    update_file(args.fn.name, owner=args.owner, name=args.name, without=args.without)
