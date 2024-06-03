''' neuronbridge_lib.py
    Function library for NeuronBridge processing
'''

from datetime import datetime
import glob
import os.path
import re
import socket
import sys
import time
from simple_term_menu import TerminalMenu

# pylint: disable=broad-exception-caught

RELEASE_LIBRARY_BASE = "/groups/scicompsoft/informatics/data/release_libraries"


def get_all_s3_objects(s3c, **base_kwargs):
    """ Generator function to handle >1000 objects
        Keyword arguments:
          s3c: S3 client instance
          base_kwargs: arguments for list_objects_v2
    """
    continuation_token = None
    while True:
        list_kwargs = dict(MaxKeys=1000, **base_kwargs)
        if continuation_token:
            list_kwargs['ContinuationToken'] = continuation_token
        response = s3c.list_objects_v2(**list_kwargs)
        yield from response.get('Contents', [])
        if not response.get('IsTruncated'):
            break
        continuation_token = response.get('NextContinuationToken')


def get_library(source='aws', **kwarg):
    """ Get NeuronBridge libraries from AWS, MongoDB, or a config file
        Keyword arguments:
          source: data source [aws, config, mongo]
          bucket: S3 bucket (source=aws)
          client: S3 client (source=aws)
          template: template (source=aws)
          config: config data (source=config)
          coll: MongoDB collection (source=mongo)
          exclude: exclusion string
        Returns:
          Library
    """
    libraries = []
    if 'exclude' not in kwarg:
        kwarg['exclude'] = None
    if source == 'aws':
        for key in ('bucket', 'client', 'template'):
            if key not in kwarg:
                print(f"Missing argument {key} to get_library({source})")
                sys.exit(0)
        paginator = kwarg['client'].get_paginator('list_objects')
        result = paginator.paginate(Bucket=kwarg['bucket'],
                                    Prefix=kwarg['template'] + '/',
                                    Delimiter='/')
        for pfx in result.search('CommonPrefixes'):
            key = pfx.get('Prefix')
            if re.search(r".+/", key) and ((not kwarg['exclude']) or (kwarg['exclude'] not in key)):
                libraries.append((key.split("/"))[1])
    elif source == 'config':
        for cdmlib in kwarg['config']:
            if kwarg['config'][cdmlib]['name'] not in libraries:
                libraries.append(kwarg['config'][cdmlib]['name'])
    elif source == 'mongo':
        results = kwarg['coll'].distinct("libraryName")
        for row in results:
            if (not kwarg['exclude']) or (kwarg['exclude'] not in row):
                libraries.append(row)
    # Display dialog
    libraries.sort()
    print("Select a NeuronBridge library:")
    terminal_menu = TerminalMenu(libraries)
    chosen = terminal_menu.show()
    if chosen is None:
        print("No NeuronBridge library selected")
        return None
    return libraries[chosen]


def get_neuronbridge_version_from_file():
    """ Get a NeuronBridge version from the release directory
        Keyword arguments:
          None
        Returns:
          NeuronBridge version
    """
    if not os.path.isdir(RELEASE_LIBRARY_BASE):
        print(f"Directory {RELEASE_LIBRARY_BASE} does not exist")
        return None
    version = [re.sub('.*/', '', path)
               for path in glob.glob(RELEASE_LIBRARY_BASE + '/v[0-9]*')]
    print("Select a NeuronBridge version:")
    terminal_menu = TerminalMenu(version)
    chosen = terminal_menu.show()
    return version[chosen] if chosen is not None else None


def get_neuronbridge_version(coll, library=None):
    ''' Allow the user to select a NeuronBridge version from MongoDB
        Keyword arguments:
          coll: MongoDB collection
        Returns:
          NeuronBridge version or None
    '''
    versions = {}
    find = {"libraryName": library} if library else {}
    results = coll.distinct("processedTags", find)
    for row in results:
        for match in ["ColorDepthSearch", "PPPMatch"]:
            if match in row:
                for ver in row[match]:
                    versions[ver] = True
    results = coll.distinct("tags", find)
    for row in results:
        if row[0].isdigit():
            versions[row] = True
    versions = list(versions.keys())
    versions.sort()
    print("Select a NeuronBridge data version:")
    terminal_menu = TerminalMenu(versions)
    chosen = terminal_menu.show()
    if chosen is None:
        print("No NeuronBridge data version selected")
        return None
    return versions[chosen]


def get_ppp_version(coll):
    ''' Allow the user to select a PPP version from MongoDB
        Keyword arguments:
          coll: MongoDB collection
        Returns:
          NeuronBridge version or None
    '''
    versions = {}
    results = coll.distinct("tags")
    for row in results:
        versions[row] = True
    versions = list(versions.keys())
    versions.sort()
    print("Select a PPP version:")
    terminal_menu = TerminalMenu(versions)
    chosen = terminal_menu.show()
    if chosen is None:
        print("No PPP version selected")
        return None
    return versions[chosen]


def get_template(s3_client, bucket):
    """ Get a NeuronBridge alignment template from the bucket
        Keyword arguments:
          s3_client: S3 client
          bucket: busket
        Returns:
          Alignment template
    """
    paginator = s3_client.get_paginator('list_objects')
    result = paginator.paginate(Bucket=bucket, Delimiter='/')
    template = []
    for prefix in result.search('CommonPrefixes'):
        key = prefix.get('Prefix')
        if re.search(r"JRC\d+.+/", key):
            template.append(key.replace("/", ""))
    if len(template) == 1:
        return template[0]
    print("Select an alignment template:")
    terminal_menu = TerminalMenu(template)
    chosen = terminal_menu.show()
    return template[chosen] if chosen is not None else None


def generate_jacs_uid(deployment_context=2, last_uid=None):
    """ Generate a JACS-style UID
        Keyword arguments:
          deployment_context: deployment context [2]
          last_uid: last UID generated [None]
        Returns:
          UID
    """
    current_time_offset = 921700000000
    max_tries = 1023
    current_index = 0
    try:
        hostname = socket.gethostname()
        ipa = socket.gethostbyname(hostname)
    except Exception:
        ipa = socket.gethostbyname('localhost')
    ip_component = int(ipa.split('.')[-1]) & 0xFF
    next_uid = None
    while (current_index <= max_tries) and not next_uid:
        time_component = int(time.time()*1000) - current_time_offset
        time_component = (time_component << 22)
        next_uid = time_component + (current_index << 12) + (deployment_context << 8) + ip_component
        if last_uid and (last_uid == next_uid):
            next_uid = None
            current_index += 1
        if not next_uid and (current_index > max_tries):
            time.sleep(0.5)
            current_index = 0
    if not next_uid:
        print("Could not generate JACS UID")
        sys.exit(-1)
    return next_uid


def update_library_status(coll, **kwargs):
    """ Update library status in Mongo
        Keyword arguments:
          coll: MongoDB collection (source=mongo)
          library: library
          manifold: manifold (prod or dev)
          method: update method
          source: data source
          images: image count
          samples: sample count
          dataset: data set
          neuprint: neuprint version
          neuronbridge:
          release: release
          tag: tag
          updateDate: update date
          updatedBy: update person
        Returns:
          True if the insert worked, False for error
    """
    if "library" not in kwargs:
        print("A library is required for update_library_status")
        return False
    if "manifold" not in kwargs:
        kwargs["manifold"] = "prod"
    if "method" not in kwargs:
        kwargs["method"] = "MongoDB"
        kwargs["source"] = "neuronMetadata"
    if "source" not in kwargs:
        if kwargs["method"] == "MongoDB":
            kwargs["source"] = "neuronMetadata"
        else:
            print("A source is required for update_library_status")
            return False
    for arg in ["images", "samples"]:
        if arg not in kwargs:
            kwargs[arg] = 0
    payload = {}
    for arg in ["images", "library", "manifold", "method",
                "samples", "source"]:
        payload[arg] = kwargs[arg]
    for arg in ["dataset", "neuprint", "neuronbridge", "release", "tag"]:
        if arg in kwargs and kwargs[arg]:
            payload[arg] = kwargs[arg]
    for arg in ["updateDate", "updatedBy"]:
        if arg in kwargs:
            payload[arg] = kwargs[arg]
    if "updateDate" not in kwargs:
        payload["updateDate"] = datetime.now()
    result = coll.insert_one(payload)
    if result.inserted_id:
        return True
    print("Could not insert record into Mongo")
    return False
